#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from validate_analysis import load_json, validate


FRAME_LABELS = {"claim_right": "请求权", "defense": "抗辩", "procedure": "程序"}
POSITION_LABELS = {"assertion": "主张", "denial": "否认", "alternative": "备位主张", "reservation": "保留意见"}
STATUS_LABELS = {
    "supported": "材料暂支持",
    "partially_supported": "材料部分支持",
    "unsupported": "当前材料未支持",
    "disputed": "存在争议",
    "missing": "材料缺失",
    "not_applicable": "待复核不适用",
    "research_required": "待研究",
    "lawyer_judgment_required": "待律师判断",
}


def _sorted_analyses(value: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(value["issue_analyses"], key=lambda item: (item["order"], item["issue_id"]))


def derive(value: dict[str, Any]) -> dict[str, Any]:
    issues = {item["issue_id"]: item for item in value["issues"]}
    analyses = _sorted_analyses(value)
    analysis_by_id = {item["issue_id"]: item for item in analyses}
    children: dict[str | None, list[str]] = {}
    for item in analyses:
        children.setdefault(item["parent_issue_id"], []).append(item["issue_id"])

    def node(issue_id: str) -> dict[str, Any]:
        analysis = analysis_by_id[issue_id]
        issue = issues[issue_id]
        return {
            "issue_id": issue_id,
            "question": issue["question"],
            "issue_status": issue["status"],
            "frame": analysis["frame"],
            "claim_ids": analysis["claim_ids"],
            "children": [node(child_id) for child_id in children.get(issue_id, [])],
        }

    element_matrix: list[dict[str, Any]] = []
    party_positions: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    research_items: list[dict[str, Any]] = []
    for analysis in analyses:
        issue_id = analysis["issue_id"]
        for element in sorted(analysis["elements"], key=lambda item: (item["order"], item["element_id"])):
            element_matrix.append({"issue_id": issue_id, **element})
            if element["status"] in {"missing", "research_required", "lawyer_judgment_required"}:
                risks.append({
                    "risk_id": f"AUTO-RISK-{element['element_id']}",
                    "risk_type": "legal_uncertainty" if element["status"] != "missing" else "fact_gap",
                    "level": "unknown",
                    "description": f"要件“{element['name']}”状态为 {element['status']}，尚不能形成律师结论。",
                    "related_ids": [issue_id, element["element_id"]],
                    "next_action": "按要件工作备注补充材料、研究法源或由律师作独立判断。",
                    "source": "derived_from_element_status",
                })
            if element["status"] == "research_required":
                research_items.append({
                    "research_id": f"AUTO-RESEARCH-{element['element_id']}",
                    "question": f"要件“{element['name']}”适用的当前有效规则及相关反向观点是什么？",
                    "reason": f"{issue_id} 的要件状态标记为 research_required。",
                    "priority": "high",
                    "status": "open",
                    "issue_id": issue_id,
                    "source": "derived_from_element_status",
                })
        for position in sorted(analysis["positions"], key=lambda item: item["position_id"]):
            party_positions.append({"issue_id": issue_id, **position})
        for risk in sorted(analysis["risks"], key=lambda item: item["risk_id"]):
            risks.append({"issue_id": issue_id, **risk, "source": "declared"})
        for item in sorted(analysis["research_items"], key=lambda entry: entry["research_id"]):
            research_items.append({"issue_id": issue_id, **item, "source": "declared"})

    explicit_related_facts = {
        fact_id for item in value["pending_confirmations"] for fact_id in item["related_fact_ids"]
    }
    pending = sorted(value["pending_confirmations"], key=lambda item: item["confirmation_id"])
    for fact in sorted(value["facts"], key=lambda item: item["fact_id"]):
        if fact["status"] in {"missing", "conflict", "unreadable", "disputed"} and fact["fact_id"] not in explicit_related_facts:
            pending.append({
                "confirmation_id": f"AUTO-CONFIRM-{fact['fact_id']}",
                "question": f"请补充或核对事实 {fact['fact_id']}，当前状态为 {fact['status']}。",
                "related_fact_ids": [fact["fact_id"]],
                "blocking": fact["status"] in {"missing", "conflict", "unreadable"},
                "source": "derived_from_fact_status",
            })

    for authority in sorted(value["authorities"], key=lambda item: item["authority_id"]):
        if authority["effect_status"] == "unknown":
            research_items.append({
                "research_id": f"AUTO-RESEARCH-{authority['authority_id']}",
                "question": f"核验法源“{authority['title']}”的现行效力、修改情况和适用时点。",
                "reason": f"法源 {authority['authority_id']} 的 effect_status 为 unknown。",
                "priority": "high",
                "status": "open",
                "issue_id": None,
                "source": "derived_from_authority_status",
            })

    frame_set = {item["frame"] for item in analyses}
    return {
        "schema_version": "1.0",
        "analysis_id": value["analysis_id"],
        "matter_id": value["matter_id"],
        "cause_of_action_status": "not_selected_by_skill",
        "final_outcome_status": "lawyer_independent_judgment_required",
        "frame_coverage": {frame: frame in frame_set for frame in ("claim_right", "defense", "procedure")},
        "issue_tree": [node(issue_id) for issue_id in children.get(None, [])],
        "element_matrix": element_matrix,
        "party_positions": party_positions,
        "risks": sorted(risks, key=lambda item: item["risk_id"]),
        "pending_confirmations": sorted(pending, key=lambda item: item["confirmation_id"]),
        "research_items": sorted(research_items, key=lambda item: item["research_id"]),
        "lawyer_judgments": sorted(value["lawyer_judgments"], key=lambda item: item["judgment_id"]),
        "domain_packs": sorted(value["domain_packs"], key=lambda item: item["pack_id"]),
    }


def validate_derived(value: dict[str, Any], skill_root: Path) -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((skill_root / "schemas" / "analysis-derived.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
    if errors:
        raise ValueError("派生结果校验失败：" + "；".join(error.message for error in errors))


def _cell(value: Any) -> str:
    if isinstance(value, list):
        text = "、".join(str(item) for item in value) if value else "—"
    elif isinstance(value, (dict, bool, int, float)) or value is None:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    return text.replace("|", "｜").replace("\n", " ")


def report_markdown(value: dict[str, Any], derived: dict[str, Any]) -> str:
    issue_by_id = {item["issue_id"]: item for item in value["issues"]}
    party_by_id = {item["party_id"]: item for item in value["parties"]}
    lines = [
        "# 案件中立分析报告",
        "",
        f"案件编号：{value['matter_id']}  ",
        f"分析编号：{value['analysis_id']}  ",
        f"分析基准日：{value['as_of_date']}  ",
        "案由：未由本 Skill 自动选择  ",
        "最终结论：待律师独立判断",
        "",
        "## 一、分析范围与边界",
        "",
        value.get("analysis_objective", "未单独说明分析目标。"),
        "",
        "本报告只编排已录入的工作底稿，不表示法院将采信某一事实、证据或法律观点。",
        "",
        "分析框架覆盖：" + "；".join(
            f"{FRAME_LABELS[frame]}={'已建立' if covered else '尚缺失，待确认是否适用'}"
            for frame, covered in derived["frame_coverage"].items()
        ),
        "",
        "## 二、当事人与请求",
        "",
    ]
    lines.extend(f"- {item['party_id']}：{item.get('name', '待确认')}｜{'、'.join(item['procedural_roles'])}｜{item['name_status']}" for item in value["parties"])
    if not value["parties"]:
        lines.append("- 尚未登记当事人。")
    lines.extend(["", "### 请求原文", ""])
    lines.extend(f"{item['order']}. {item['claim_id']}：{item['text_verbatim']}（{item['status']}）" for item in sorted(value["claims"], key=lambda item: (item["order"], item["claim_id"])))
    if not value["claims"]:
        lines.append("- 尚未登记请求原文。")

    lines.extend(["", "## 三、事实记录", "", "| 事实编号 | 字段 | 原始值 | 状态 | 来源数 |", "| --- | --- | --- | --- | --- |"])
    stable_facts = [item for item in value["facts"] if item["status"] not in {"disputed", "conflict", "missing", "unreadable"}]
    for fact in stable_facts:
        lines.append(f"| {_cell(fact['fact_id'])} | {_cell(fact.get('field', '—'))} | {_cell(fact['raw_value'])} | {_cell(fact['status'])} | {len(fact['source_spans'])} |")
    if not stable_facts:
        lines.append("| — | — | 尚无非争议事实 | — | 0 |")

    lines.extend(["", "## 四、争议事实与对立主张", ""])
    disputed_facts = [item for item in value["facts"] if item["status"] in {"disputed", "conflict", "missing", "unreadable"}]
    for fact in disputed_facts:
        lines.append(f"- {fact['fact_id']}：{_cell(fact['raw_value'])}｜{fact['status']}")
    if not disputed_facts:
        lines.append("- 当前事实账本未标记争议、冲突、缺失或无法识读事项；仍须律师核验。")
    lines.extend(["", "| 争点 | 当事人 | 类型 | 主张原文 | 事实/证据/法源 |", "| --- | --- | --- | --- | --- |"])
    for position in derived["party_positions"]:
        party = party_by_id.get(position["party_id"], {})
        refs = position["fact_ids"] + position["evidence_ids"] + position["authority_ids"]
        lines.append(f"| {_cell(position['issue_id'])} | {_cell(party.get('name', position['party_id']))} | {_cell(POSITION_LABELS[position['position_type']])} | {_cell(position['statement'])} | {_cell(refs)} |")
    if not derived["party_positions"]:
        lines.append("| — | — | — | 尚未登记各方主张 | — |")

    lines.extend(["", "## 五、证据记录", "", "| 证据 | 名称 | 事实指针 | 真实性/合法性/关联性 | 核验 |", "| --- | --- | --- | --- | --- |"])
    for item in value["evidence"]:
        three = f"{item.get('authenticity', 'unreviewed')}/{item.get('legality', 'unreviewed')}/{item.get('relevance', 'unreviewed')}"
        lines.append(f"| {_cell(item['evidence_id'])} | {_cell(item['name'])} | {_cell(item.get('fact_ids', []))} | {_cell(three)} | {_cell(item['verification_status'])} |")
    if not value["evidence"]:
        lines.append("| — | 尚未登记证据 | — | — | — |")

    lines.extend(["", "## 六、法源记录", "", "| 法源 | 名称 | 类型 | 效力 | 核验时间 | 回查地址 |", "| --- | --- | --- | --- | --- | --- |"])
    for item in value["authorities"]:
        lines.append(f"| {_cell(item['authority_id'])} | {_cell(item['title'])} | {_cell(item['authority_type'])} | {_cell(item['effect_status'])} | {_cell(item['verified_at'])} | {_cell(item['source_url'])} |")
    if not value["authorities"]:
        lines.append("| — | 尚未登记已核验法源 | — | — | — | — |")

    lines.extend(["", "## 七、争点树", ""])
    def add_nodes(nodes: list[dict[str, Any]], depth: int = 0) -> None:
        for item in nodes:
            lines.append(f"{'  ' * depth}- [{FRAME_LABELS[item['frame']]}] {item['issue_id']}：{item['question']}（{item['issue_status']}）")
            add_nodes(item["children"], depth + 1)
    add_nodes(derived["issue_tree"])

    lines.extend(["", "## 八、要件矩阵", "", "| 争点 | 要件 | 工作状态 | 举证责任 | 事实 | 证据 | 法源 | 反方意见 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for item in derived["element_matrix"]:
        lines.append(f"| {_cell(item['issue_id'])} | {_cell(item['name'])} | {_cell(STATUS_LABELS[item['status']])} | {_cell(item['burden_party_ids'])} | {_cell(item['fact_ids'])} | {_cell(item['evidence_ids'])} | {_cell(item['authority_ids'])} | {_cell(item['opposing_arguments'])} |")
    if not derived["element_matrix"]:
        lines.append("| — | 尚未登记要件 | — | — | — | — | — | — |")

    lines.extend(["", "## 九、风险与下一步", ""])
    lines.extend(f"- [{item['level']}/{item['risk_type']}] {item['risk_id']}：{item['description']}下一步：{item['next_action']}" for item in derived["risks"])
    if not derived["risks"]:
        lines.append("- 尚未登记风险；这不表示案件无风险。")

    lines.extend(["", "## 十、待确认事项", ""])
    lines.extend(f"- {'[阻断]' if item['blocking'] else '[非阻断]'} {item['confirmation_id']}：{item['question']}" for item in derived["pending_confirmations"])
    if not derived["pending_confirmations"]:
        lines.append("- 当前未登记待确认事项；仍须律师与当事人逐项复核。")

    lines.extend(["", "## 十一、待研究事项", ""])
    lines.extend(f"- [{item['priority']}/{item['status']}] {item['research_id']}：{item['question']}原因：{item['reason']}" for item in derived["research_items"])
    if not derived["research_items"]:
        lines.append("- 当前未登记待研究事项；仍应核验法律更新。")

    lines.extend(["", "## 十二、律师独立判断区", ""])
    for item in derived["lawyer_judgments"]:
        if item["status"] == "provided":
            lines.append(f"- [已提供] {item['question']}：{item['content']}（复核人：{item['reviewed_by']}，{item['reviewed_at']}）")
        else:
            lines.append(f"- [待判断] {item['judgment_id']}：{item['question']}")
    if not derived["lawyer_judgments"]:
        lines.append("- 尚未录入律师判断问题；本报告不含最终法律结论。")

    lines.extend(["", "## 十三、已加载领域知识包", ""])
    lines.extend(f"- {item['pack_id']}@{item['version']}：{_cell(item['loaded_reference_ids'])}" for item in derived["domain_packs"])
    if not derived["domain_packs"]:
        lines.append("- 未加载领域知识包。")

    lines.extend([
        "",
        "## 十四、使用提示",
        "",
        "AI 生成的法律分析仅供学习和工作底稿整理参考，不得直接作为对外意见、诉讼策略或提交材料。使用前必须由执业律师对事实、证据、程序与法律适用逐项审查。",
    ])
    return "\n".join(lines) + "\n"


def build(input_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    value = load_json(input_path)
    skill_root = Path(__file__).resolve().parent.parent
    validation = validate(value, skill_root)
    if not validation["ok"]:
        raise ValueError("；".join(validation["errors"]))
    derived = derive(value)
    validate_derived(derived, skill_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-case-analysis-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        (temp / "analysis.normalized.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "analysis-derived.json").write_text(json.dumps(derived, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "案件中立分析报告.md").write_text(report_markdown(value, derived), encoding="utf-8")
        temp.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成中国案件中立结构化分析")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.input, args.output)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] 已生成案件中立分析：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
