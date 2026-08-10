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
    "determine_actionability": "不得自动认定行政行为可诉性",
    "determine_jurisdiction": "不得自动认定管辖",
    "determine_reconsideration_precondition": "不得自动认定复议前置",
    "calculate_or_determine_deadline": "不得自动计算或认定起诉期限",
    "contact_or_submit_external": "不得自动联系、发送或提交",
    "sign_or_stamp": "不得自动签名或盖章",
}
PROHIBITIONS = list(PROHIBITED_ACTIONS.values())
ALLOWED_ACTIONS = {"generate_workbench"}


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
    schema = load_json(skill_root / "schemas" / "admin-litigation-input.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}：{error.message}"
        for error in sorted(validator.iter_errors(value), key=lambda error: tuple(str(part) for part in error.absolute_path))
    ]
    if errors:
        return errors

    collections = {
        "当事人": (value["parties"], "party_id"),
        "文书": (value["documents"], "document_id"),
        "程序事件": (value["procedure_events"], "event_id"),
        "送达事件": (value["service_events"], "service_id"),
        "法源": (value["authorities"], "authority_id"),
        "期限规则": (value["filing_deadline_rules"], "rule_id"),
        "证据": (value["evidence"], "evidence_id"),
        "诉请": (value["claims"], "claim_id"),
    }
    for label, (items, key) in collections.items():
        duplicated = _duplicates(items, key)
        if duplicated:
            errors.append(f"{label}编号重复：{'、'.join(duplicated)}")
    candidate_ids = [
        item["candidate_id"]
        for field in ("actionability_candidates", "jurisdiction_candidates", "reconsideration_precondition_candidates")
        for item in value[field]
    ]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("可诉性、管辖和复议前置候选编号必须全局唯一")

    party_ids = {item["party_id"] for item in value["parties"]}
    document_ids = {item["document_id"] for item in value["documents"]}
    authority_ids = {item["authority_id"] for item in value["authorities"]}
    event_ids = {item["event_id"] for item in value["procedure_events"]}
    act_id = value["administrative_act"]["act_id"]

    for authority in value["authorities"]:
        if not _official_url(authority["source_url"]):
            errors.append(f"法源 {authority['authority_id']} 的 URL 不是中国官方机关站点")
    act = value["administrative_act"]
    if act["issuing_body_party_id"] not in party_ids:
        errors.append("行政行为引用不存在的作出主体")
    missing_relatives = set(act["relative_party_ids"]) - party_ids
    if missing_relatives:
        errors.append("行政行为引用不存在的相对人：" + "、".join(sorted(missing_relatives)))
    missing_docs = set(act["document_ids"]) - document_ids
    if missing_docs:
        errors.append("行政行为引用不存在的文书：" + "、".join(sorted(missing_docs)))
    for event in value["procedure_events"]:
        missing = set(event["document_ids"]) - document_ids
        if missing:
            errors.append(f"程序事件 {event['event_id']} 引用不存在的文书：{'、'.join(sorted(missing))}")
    for event in value["service_events"]:
        if event["recipient_party_id"] not in party_ids:
            errors.append(f"送达事件 {event['service_id']} 引用不存在的受送达人")
        missing = set(event["document_ids"]) - document_ids
        if missing:
            errors.append(f"送达事件 {event['service_id']} 引用不存在的文书：{'、'.join(sorted(missing))}")
    for field in ("actionability_candidates", "jurisdiction_candidates", "reconsideration_precondition_candidates"):
        for candidate in value[field]:
            missing = set(candidate["authority_ids"]) - authority_ids
            if missing:
                errors.append(f"候选项 {candidate['candidate_id']} 引用不存在的法源：{'、'.join(sorted(missing))}")
    for rule in value["filing_deadline_rules"]:
        missing_events = set(rule["start_event_ids"]) - event_ids
        missing_authorities = set(rule["authority_ids"]) - authority_ids
        if missing_events:
            errors.append(f"期限规则 {rule['rule_id']} 引用不存在的起算事件：{'、'.join(sorted(missing_events))}")
        if missing_authorities:
            errors.append(f"期限规则 {rule['rule_id']} 引用不存在的法源：{'、'.join(sorted(missing_authorities))}")
    for evidence in value["evidence"]:
        missing = set(evidence["document_ids"]) - document_ids
        if missing:
            errors.append(f"证据 {evidence['evidence_id']} 引用不存在的文书：{'、'.join(sorted(missing))}")
    for claim in value["claims"]:
        if claim["target_act_id"] != act_id:
            errors.append(f"诉请 {claim['claim_id']} 指向不存在的行政行为")
        missing = set(claim["authority_ids"]) - authority_ids
        if missing:
            errors.append(f"诉请 {claim['claim_id']} 引用不存在的法源：{'、'.join(sorted(missing))}")
    prohibited = sorted(set(value["requested_actions"]) & set(PROHIBITED_ACTIONS))
    if prohibited:
        errors.append("包含禁止动作：" + "；".join(PROHIBITED_ACTIONS[item] for item in prohibited))
    unknown = sorted(set(value["requested_actions"]) - set(PROHIBITED_ACTIONS) - ALLOWED_ACTIONS)
    if unknown:
        errors.append("包含未识别动作，按安全默认阻断：" + "、".join(unknown))
    return errors


def derive(value: dict[str, Any]) -> dict[str, Any]:
    escalations: list[dict[str, Any]] = []
    act = value["administrative_act"]
    if not act["document_ids"] or act["act_date"] is None:
        escalations.append({
            "escalation_id": f"ESC-{act['act_id']}",
            "severity": "high",
            "reason": "行政行为日期或来源文书不完整，须律师核验行为对象和程序材料。",
            "related_ids": [act["act_id"], *sorted(act["document_ids"])],
        })
    for event in sorted(value["service_events"], key=lambda item: item["service_id"]):
        if event["service_date"] is None or event["status"] != "recorded":
            escalations.append({
                "escalation_id": f"ESC-{event['service_id']}",
                "severity": "high",
                "reason": "送达日期或状态不完整，可能影响程序及期限判断，须律师核验原始凭证。",
                "related_ids": [event["service_id"], event["recipient_party_id"], *sorted(event["document_ids"])],
            })
    for rule in sorted(value["filing_deadline_rules"], key=lambda item: item["rule_id"]):
        if not rule["start_event_ids"] or rule["candidate_due_date"] is None or rule["status"] != "lawyer_reviewed":
            escalations.append({
                "escalation_id": f"ESC-{rule['rule_id']}",
                "severity": "high",
                "reason": "起诉期限规则、起算事件或候选日期尚未由律师确认，脚本不计算或认定期限。",
                "related_ids": [rule["rule_id"], *sorted(rule["start_event_ids"]), *sorted(rule["authority_ids"])],
            })
    for field, label in (
        ("actionability_candidates", "可诉性"),
        ("jurisdiction_candidates", "管辖"),
        ("reconsideration_precondition_candidates", "复议前置"),
    ):
        for candidate in sorted(value[field], key=lambda item: item["candidate_id"]):
            if candidate["status"] != "lawyer_reviewed":
                escalations.append({
                    "escalation_id": f"ESC-{candidate['candidate_id']}",
                    "severity": "high",
                    "reason": f"{label}仅为候选问题，尚未由律师作出独立判断。",
                    "related_ids": [candidate["candidate_id"], *sorted(candidate["authority_ids"])],
                })
    for authority in sorted(value["authorities"], key=lambda item: item["authority_id"]):
        if authority["effect_status"] == "unknown":
            escalations.append({
                "escalation_id": f"ESC-{authority['authority_id']}",
                "severity": "high",
                "reason": "法源效力状态未知，使用前须重新核验官方来源和适用时点。",
                "related_ids": [authority["authority_id"]],
            })

    claims = sorted(value["claims"], key=lambda item: item["claim_id"])
    return {
        "schema_version": "1.0",
        "matter_id": value["matter_id"],
        "as_of_date": value["as_of_date"],
        "review_state": "lawyer_review_required",
        "external_action_state": "not_performed",
        "conclusion_states": {
            "actionability": "not_determined_by_skill",
            "jurisdiction": "not_determined_by_skill",
            "reconsideration_precondition": "not_determined_by_skill",
            "filing_deadline": "not_determined_by_skill",
        },
        "parties": sorted(value["parties"], key=lambda item: item["party_id"]),
        "documents": sorted(value["documents"], key=lambda item: item["document_id"]),
        "administrative_act": value["administrative_act"],
        "procedure_events": sorted(value["procedure_events"], key=lambda item: item["event_id"]),
        "service_events": sorted(value["service_events"], key=lambda item: item["service_id"]),
        "authorities": sorted(value["authorities"], key=lambda item: item["authority_id"]),
        "actionability_candidates": sorted(value["actionability_candidates"], key=lambda item: item["candidate_id"]),
        "jurisdiction_candidates": sorted(value["jurisdiction_candidates"], key=lambda item: item["candidate_id"]),
        "reconsideration_precondition_candidates": sorted(value["reconsideration_precondition_candidates"], key=lambda item: item["candidate_id"]),
        "filing_deadline_rules": sorted(value["filing_deadline_rules"], key=lambda item: item["rule_id"]),
        "evidence": sorted(value["evidence"], key=lambda item: item["evidence_id"]),
        "claims": claims,
        "claim_conservation": {"input_count": len(value["claims"]), "output_count": len(claims), "verbatim_preserved": True},
        "human_escalations": sorted(escalations, key=lambda item: item["escalation_id"]),
        "prohibitions": PROHIBITIONS,
    }


def validate_output(result: dict[str, Any], original_claims: list[dict[str, Any]], skill_root: Path) -> None:
    schema = load_json(skill_root / "schemas" / "admin-litigation-output.schema.json")
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(result))
    input_claims = {item["claim_id"]: item["text_verbatim"] for item in original_claims}
    output_claims = {item["claim_id"]: item["text_verbatim"] for item in result["claims"]}
    if input_claims != output_claims:
        errors.append(ValueError("诉请编号或原文不守恒"))
    if errors:
        raise ValueError("输出校验失败：" + "；".join(getattr(error, "message", str(error)) for error in errors))


def _candidates(lines: list[str], title: str, values: list[dict[str, Any]]) -> None:
    lines.extend(["", f"### {title}", ""])
    if values:
        for item in values:
            lines.append(f"- {item['candidate_id']}：{item['statement']}｜状态 {item['status']}｜法源 {'、'.join(item['authority_ids'])}")
    else:
        lines.append("- 尚未登记候选问题；不得据此作出结论。")


def markdown_report(result: dict[str, Any]) -> str:
    act = result["administrative_act"]
    lines = [
        "# 行政诉讼工作底稿",
        "",
        f"案件编号：{result['matter_id']}  ",
        f"材料基准日：{result['as_of_date']}  ",
        "复核状态：lawyer_review_required  ",
        "外部动作：未执行",
        "",
        "## 一、行政主体、相对人与行政行为",
        "",
    ]
    for party in result["parties"]:
        lines.append(f"- {party['party_id']}：{party['name_masked']}｜角色 {party['role']}｜主体状态 {party['qualification_status']}")
    lines.extend(["", f"- 行政行为 {act['act_id']}：{act['act_type_verbatim']}｜{act['content_verbatim']}｜日期 {act['act_date'] or '待确认'}"])
    lines.extend(["", "## 二、程序与送达", ""])
    for event in result["procedure_events"]:
        lines.append(f"- {event['event_id']}：{event['description_verbatim']}｜日期 {event['event_date'] or '待确认'}｜状态 {event['status']}")
    for event in result["service_events"]:
        lines.append(f"- {event['service_id']}：向 {event['recipient_party_id']} 以 {event['method_verbatim']} 送达｜日期 {event['service_date'] or '待确认'}｜状态 {event['status']}")
    lines.extend(["", "## 三、候选法律问题", "", "本节仅列候选，不表示可诉性、管辖或复议前置已经确定。"])
    _candidates(lines, "可诉性候选", result["actionability_candidates"])
    _candidates(lines, "管辖候选", result["jurisdiction_candidates"])
    _candidates(lines, "复议前置候选", result["reconsideration_precondition_candidates"])
    lines.extend(["", "## 四、起诉期限规则输入", "", "脚本不计算或认定起诉期限。"])
    for rule in result["filing_deadline_rules"]:
        lines.append(f"- {rule['rule_id']}：{rule['rule_text_verbatim']}｜起算事件 {'、'.join(rule['start_event_ids']) or '待确认'}｜候选日期 {rule['candidate_due_date'] or '待律师核验'}｜状态 {rule['status']}")
    lines.extend(["", "## 五、证据", ""])
    for item in result["evidence"]:
        lines.append(f"- {item['evidence_id']}：{item['name']}｜{item['fact_statement']}｜真实性 {item['authenticity']}｜合法性 {item['legality']}｜关联性 {item['relevance']}")
    if not result["evidence"]:
        lines.append("- 尚未登记证据。")
    lines.extend(["", "## 六、诉请原文", ""])
    for item in result["claims"]:
        lines.append(f"- {item['claim_id']}：{item['text_verbatim']}｜状态 {item['status']}")
    lines.append(f"- 守恒校验：输入 {result['claim_conservation']['input_count']} 项，输出 {result['claim_conservation']['output_count']} 项，原文已保留。")
    lines.extend(["", "## 七、人工升级事项", ""])
    for item in result["human_escalations"]:
        lines.append(f"- [{item['severity']}] {item['escalation_id']}：{item['reason']}｜关联 {'、'.join(item['related_ids'])}")
    if not result["human_escalations"]:
        lines.append("- 当前未自动识别升级事项；仍须律师逐项核验。")
    lines.extend(["", "## 八、法源", ""])
    for item in result["authorities"]:
        lines.append(f"- {item['authority_id']}：{item['title']}｜效力 {item['effect_status']}｜核验 {item['verified_at']}｜{item['source_url']}")
    lines.extend(["", "## 九、使用边界", ""])
    lines.extend(f"- {item}" for item in result["prohibitions"])
    lines.extend(["", "AI 生成内容仅为行政诉讼工作底稿，不得直接提交、发送或作为最终法律意见。全部事实、程序、送达、法源、期限、诉请和策略必须由执业律师逐项审查。", ""])
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
    validate_output(result, value["claims"], skill_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (temp / "admin-litigation-workbench.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (temp / "行政诉讼工作底稿.md").write_text(markdown_report(result), encoding="utf-8")
        temp.replace(output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="生成需律师人工复核的行政诉讼工作底稿")
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
