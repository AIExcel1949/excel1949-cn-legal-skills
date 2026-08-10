#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker


PROHIBITED_ACTIONS = {
    "predict_sentence": "不预测刑期，不作刑期预测或量刑结果推演",
    "evade_investigation": "不得提供规避侦查方法",
    "fabricate_evidence": "不得伪造证据",
    "contact_authority": "不得自动联系办案机关",
    "submit_external": "不得自动对外发送或提交",
    "sign_or_stamp": "不得自动签名或盖章",
}
PROHIBITIONS = list(PROHIBITED_ACTIONS.values())
ALLOWED_ACTIONS = {"generate_workbench"}
RESTRICTED = {"detained", "arrested", "residential_surveillance", "restricted_other"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入必须是 JSON 对象")
    return value


def _official_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower().rstrip(".")
    return host == "gov.cn" or host.endswith(".gov.cn")


def _duplicates(items: list[dict[str, Any]], key: str) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        item_id = item[key]
        if item_id in seen:
            duplicates.add(item_id)
        seen.add(item_id)
    return sorted(duplicates)


def validate_input(value: dict[str, Any], skill_root: Path) -> list[str]:
    schema = load_json(skill_root / "schemas" / "criminal-defense-input.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}：{error.message}"
        for error in sorted(validator.iter_errors(value), key=lambda error: tuple(str(part) for part in error.absolute_path))
    ]
    if errors:
        return errors

    collections = {
        "文书": (value["official_documents"], "document_id"),
        "指控记录": (value["accusations"], "accusation_id"),
        "法源": (value["authorities"], "authority_id"),
        "期限规则": (value["deadline_rules"], "rule_id"),
        "证据": (value["evidence_reviews"], "evidence_id"),
        "排除线索": (value["exclusion_clues"], "clue_id"),
        "羁押会见任务": (value["liberty_and_meeting_tasks"], "task_id"),
    }
    for label, (items, key) in collections.items():
        duplicated = _duplicates(items, key)
        if duplicated:
            errors.append(f"{label}编号重复：{'、'.join(duplicated)}")
    candidate_ids: list[str] = []
    for field in ("element_candidates", "sentencing_candidates", "defense_positions"):
        candidate_ids.extend(item["candidate_id"] for item in value[field])
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("候选项编号必须在三个候选分区中全局唯一")

    document_ids = {item["document_id"] for item in value["official_documents"]}
    authority_ids = {item["authority_id"] for item in value["authorities"]}
    evidence_ids = {item["evidence_id"] for item in value["evidence_reviews"]}
    rule_ids = {item["rule_id"] for item in value["deadline_rules"]}

    for authority in value["authorities"]:
        if not _official_url(authority["source_url"]):
            errors.append(f"法源 {authority['authority_id']} 的 URL 不是中国官方机关站点")
    for accusation in value["accusations"]:
        missing = set(accusation["source_document_ids"]) - document_ids
        if missing:
            errors.append(f"指控记录 {accusation['accusation_id']} 引用不存在的文书：{'、'.join(sorted(missing))}")
    for rule in value["deadline_rules"]:
        missing = set(rule["authority_ids"]) - authority_ids
        if missing:
            errors.append(f"期限规则 {rule['rule_id']} 引用不存在的法源：{'、'.join(sorted(missing))}")
    for evidence in value["evidence_reviews"]:
        missing = set(evidence["source_document_ids"]) - document_ids
        if missing:
            errors.append(f"证据 {evidence['evidence_id']} 引用不存在的文书：{'、'.join(sorted(missing))}")
    for clue in value["exclusion_clues"]:
        missing_docs = set(clue["source_document_ids"]) - document_ids
        missing_evidence = set(clue["evidence_ids"]) - evidence_ids
        if missing_docs:
            errors.append(f"排除线索 {clue['clue_id']} 引用不存在的文书：{'、'.join(sorted(missing_docs))}")
        if missing_evidence:
            errors.append(f"排除线索 {clue['clue_id']} 引用不存在的证据：{'、'.join(sorted(missing_evidence))}")
    for task in value["liberty_and_meeting_tasks"]:
        missing = set(task["deadline_rule_ids"]) - rule_ids
        if missing:
            errors.append(f"任务 {task['task_id']} 引用不存在的期限规则：{'、'.join(sorted(missing))}")
    for field in ("element_candidates", "sentencing_candidates", "defense_positions"):
        for candidate in value[field]:
            missing_docs = set(candidate["source_document_ids"]) - document_ids
            missing_evidence = set(candidate["evidence_ids"]) - evidence_ids
            missing_authorities = set(candidate["authority_ids"]) - authority_ids
            missing = sorted(missing_docs | missing_evidence | missing_authorities)
            if missing:
                errors.append(f"候选项 {candidate['candidate_id']} 引用不存在的对象：{'、'.join(missing)}")
    prohibited = sorted(set(value["requested_actions"]) & set(PROHIBITED_ACTIONS))
    if prohibited:
        errors.append("包含禁止动作：" + "；".join(PROHIBITED_ACTIONS[item] for item in prohibited))
    unknown = sorted(set(value["requested_actions"]) - set(PROHIBITED_ACTIONS) - ALLOWED_ACTIONS)
    if unknown:
        errors.append("包含未识别动作，按安全默认阻断：" + "、".join(unknown))
    return errors


def derive(value: dict[str, Any]) -> dict[str, Any]:
    escalations: list[dict[str, Any]] = []
    for task in sorted(value["liberty_and_meeting_tasks"], key=lambda item: item["task_id"]):
        liberty = task["liberty_status"]
        if liberty in RESTRICTED:
            escalations.append({
                "escalation_id": f"ESC-{task['task_id']}",
                "severity": "critical",
                "reason": "存在现实人身自由限制，须由承办律师立即核验强制措施、场所、文书和救济节点。",
                "related_ids": [task["task_id"]],
            })
        elif liberty in {"possibly_restricted", "unknown"} or task["status"] == "blocked":
            escalations.append({
                "escalation_id": f"ESC-{task['task_id']}",
                "severity": "high",
                "reason": "人身自由状态或会见任务存在不确定或受阻情形，须律师人工核验。",
                "related_ids": [task["task_id"]],
            })
    for rule in sorted(value["deadline_rules"], key=lambda item: item["rule_id"]):
        if rule["liberty_related"] and (not rule["start_event"] or not rule["candidate_due_date"]):
            escalations.append({
                "escalation_id": f"ESC-{rule['rule_id']}",
                "severity": "high",
                "reason": "人身自由相关期限的起算事件或候选日期不完整，脚本不作计算，须律师立即核验。",
                "related_ids": [rule["rule_id"], *sorted(rule["authority_ids"])],
            })
    for clue in sorted(value["exclusion_clues"], key=lambda item: item["clue_id"]):
        escalations.append({
            "escalation_id": f"ESC-{clue['clue_id']}",
            "severity": "high",
            "reason": "存在证据合法性或排除线索，只能作为调查候选，须律师决定核查和程序动作。",
            "related_ids": [clue["clue_id"], *sorted(clue["evidence_ids"])],
        })

    return {
        "schema_version": "1.0",
        "matter_id": value["matter_id"],
        "as_of_date": value["as_of_date"],
        "stage": value["stage"],
        "review_state": "lawyer_review_required",
        "external_action_state": "not_performed",
        "accusation_status": "verbatim_record_only_not_final_finding",
        "official_documents": sorted(value["official_documents"], key=lambda item: item["document_id"]),
        "accusations": sorted(value["accusations"], key=lambda item: item["accusation_id"]),
        "authorities": sorted(value["authorities"], key=lambda item: item["authority_id"]),
        "deadline_rules": sorted(value["deadline_rules"], key=lambda item: item["rule_id"]),
        "element_candidates": sorted(value["element_candidates"], key=lambda item: item["candidate_id"]),
        "evidence_reviews": sorted(value["evidence_reviews"], key=lambda item: item["evidence_id"]),
        "exclusion_clues": sorted(value["exclusion_clues"], key=lambda item: item["clue_id"]),
        "liberty_and_meeting_tasks": sorted(value["liberty_and_meeting_tasks"], key=lambda item: item["task_id"]),
        "sentencing_candidates": sorted(value["sentencing_candidates"], key=lambda item: item["candidate_id"]),
        "defense_positions": sorted(value["defense_positions"], key=lambda item: item["candidate_id"]),
        "human_escalations": sorted(escalations, key=lambda item: item["escalation_id"]),
        "prohibitions": PROHIBITIONS,
    }


def validate_output(value: dict[str, Any], skill_root: Path) -> None:
    schema = load_json(skill_root / "schemas" / "criminal-defense-output.schema.json")
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise ValueError("输出校验失败：" + "；".join(error.message for error in errors))


def _items(lines: list[str], values: list[dict[str, Any]], text_key: str, empty: str) -> None:
    if not values:
        lines.append(f"- {empty}")
        return
    for item in values:
        item_id = next(value for key, value in item.items() if key.endswith("_id"))
        lines.append(f"- {item_id}：{item[text_key]}")


def markdown_report(result: dict[str, Any]) -> str:
    stage_labels = {"investigation": "侦查", "review_prosecution": "审查起诉", "trial": "审判", "unknown": "阶段待确认"}
    lines = [
        "# 刑事辩护工作底稿",
        "",
        f"案件编号：{result['matter_id']}  ",
        f"材料基准日：{result['as_of_date']}  ",
        f"办案阶段：{stage_labels[result['stage']]}  ",
        "复核状态：lawyer_review_required  ",
        "外部动作：未执行",
        "",
        "## 一、办案机关文书与指控原文",
        "",
        "以下内容仅为文书原文登记，不表示事实认定、罪名成立或最终裁判。",
        "",
    ]
    for item in result["accusations"]:
        kind = "指控事实原文" if item["kind"] == "alleged_fact" else "涉嫌罪名原文"
        lines.append(f"- [{kind}] {item['accusation_id']}：{item['text_verbatim']}｜来源：{'、'.join(item['source_document_ids'])}")
    if not result["accusations"]:
        lines.append("- 尚未登记指控原文。")
    lines.extend(["", "## 二、构成要件候选", ""])
    _items(lines, result["element_candidates"], "statement", "尚未登记构成要件候选。")
    lines.extend(["", "## 三、证据审查与排除线索", ""])
    for item in result["evidence_reviews"]:
        lines.append(f"- {item['evidence_id']}：{item['name']}｜真实性 {item['authenticity']}｜合法性 {item['legality']}｜关联性 {item['relevance']}｜{item['notes']}")
    if not result["evidence_reviews"]:
        lines.append("- 尚未登记证据审查事项。")
    for item in result["exclusion_clues"]:
        lines.append(f"- [排除线索候选] {item['clue_id']}：{item['description']}｜状态 {item['status']}")
    lines.extend(["", "## 四、羁押、会见与期限任务", ""])
    for item in result["liberty_and_meeting_tasks"]:
        lines.append(f"- {item['task_id']}：{item['description']}｜人身自由 {item['liberty_status']}｜任务 {item['status']}")
    for item in result["deadline_rules"]:
        lines.append(f"- {item['rule_id']}：{item['name']}｜规则原文：{item['rule_text_verbatim']}｜起算：{item['start_event'] or '待确认'}｜候选日期：{item['candidate_due_date'] or '待律师核验'}")
    lines.extend(["", "## 五、量刑情节候选", ""])
    _items(lines, result["sentencing_candidates"], "statement", "尚未登记量刑情节候选；不作刑期预测。")
    lines.extend(["", "## 六、辩护观点工作区", ""])
    _items(lines, result["defense_positions"], "statement", "尚未登记辩护观点。")
    lines.extend(["", "## 七、人工升级事项", ""])
    for item in result["human_escalations"]:
        lines.append(f"- [{item['severity']}] {item['escalation_id']}：{item['reason']}｜关联：{'、'.join(item['related_ids'])}")
    if not result["human_escalations"]:
        lines.append("- 当前未自动识别升级事项；这不表示案件不存在人身自由或程序风险。")
    lines.extend(["", "## 八、法源记录", ""])
    for item in result["authorities"]:
        lines.append(f"- {item['authority_id']}：{item['title']}｜效力 {item['effect_status']}｜核验 {item['verified_at']}｜{item['source_url']}")
    lines.extend(["", "## 九、使用边界", ""])
    lines.extend(f"- {item}" for item in result["prohibitions"])
    lines.extend(["", "AI 生成内容仅为刑事辩护工作底稿，不得直接提交、发送或作为最终法律意见。全部事实、证据、法源、期限与策略必须由执业律师逐项审查。", ""])
    return "\n".join(lines)


def build(input_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    skill_root = Path(__file__).resolve().parent.parent
    value = load_json(input_path)
    errors = validate_input(value, skill_root)
    if errors:
        raise ValueError("；".join(errors))
    result = derive(value)
    validate_output(result, skill_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (temp / "criminal-defense-workbench.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (temp / "刑事辩护工作底稿.md").write_text(markdown_report(result), encoding="utf-8")
        temp.replace(output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="生成需律师人工复核的刑事辩护工作底稿")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.input, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
