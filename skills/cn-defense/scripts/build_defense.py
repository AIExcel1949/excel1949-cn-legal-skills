#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
NOTICES = [
    "AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。",
    "使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。",
    "AI 不能替代律师对案件具体情况进行独立法律判断。",
    "本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。",
    "AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。",
]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入 JSON 顶层必须为对象")
    return value


def schema(name: str) -> dict[str, Any]:
    return load_json(ROOT / "schemas" / name)


def validate_input(value: dict[str, Any]) -> dict[str, Any]:
    validator = Draft202012Validator(schema("defense-input.schema.json"), format_checker=FormatChecker())
    errors = [f"{'.'.join(str(x) for x in e.absolute_path) or '$'}: {e.message}" for e in sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path))]
    if errors:
        return {"ok": False, "errors": errors}
    matter_id = value["matter_id"]
    for key in ("case_analysis", "evidence_map"):
        if value[key]["matter_id"] != matter_id:
            errors.append(f"{key}.matter_id 与顶层 matter_id 不一致")
    if value["research_report"]["task"]["matter_id"] != matter_id:
        errors.append("research_report.task.matter_id 与顶层 matter_id 不一致")

    claims = value["complaint"]["claims"]
    claim_ids = [x["claim_id"] for x in claims]
    if len(claim_ids) != len(set(claim_ids)):
        errors.append("原告诉请 claim_id 存在重复")
    responses = value["defense_request"]["responses"]
    response_claim_ids = [x["claim_id"] for x in responses]
    if len(response_claim_ids) != len(set(response_claim_ids)):
        errors.append("同一诉请存在多个答辩响应")
    for response in responses:
        if response["claim_id"] not in claim_ids:
            errors.append(f"答辩 {response['response_id']} 引用不存在的诉请 {response['claim_id']}")

    facts = value["defense_request"]["defensive_facts"]
    fact_ids = [x["fact_id"] for x in facts]
    if len(fact_ids) != len(set(fact_ids)):
        errors.append("答辩事实 fact_id 存在重复")
    evidence_ids = {str(x.get("evidence_id")) for x in value["evidence_map"]["matrix"] if x.get("evidence_id")}
    authority_ids = {x["record_id"] for x in value["research_report"]["records"]}
    linked_items = responses + value["defense_request"]["independent_defenses"]
    for item in linked_items:
        for fact_id in item["fact_ids"]:
            if fact_id not in fact_ids:
                errors.append(f"{item.get('response_id', item.get('defense_id'))} 引用不存在的答辩事实 {fact_id}")
        for evidence_id in item["evidence_ids"]:
            if evidence_id not in evidence_ids:
                errors.append(f"{item.get('response_id', item.get('defense_id'))} 引用不存在的证据 {evidence_id}")
        for authority_id in item["authority_ids"]:
            if authority_id not in authority_ids:
                errors.append(f"{item.get('response_id', item.get('defense_id'))} 引用不存在的法源 {authority_id}")
    for fact in facts:
        for evidence_id in fact["evidence_ids"]:
            if evidence_id not in evidence_ids:
                errors.append(f"事实 {fact['fact_id']} 引用不存在的证据 {evidence_id}")
    return {"ok": not errors, "errors": errors}


def derive(value: dict[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    evidence_gaps: list[dict[str, str]] = []
    for index, item in enumerate(value["case_analysis"]["pending_confirmations"], 1):
        blockers.append({"code": "pending_confirmation", "target": str(item.get("confirmation_id", index)), "message": "案件分析存在待确认事项"})
    for index, item in enumerate(value["evidence_map"]["gaps"], 1):
        gap = {"code": str(item.get("gap_type", "evidence_gap")), "target": str(item.get("target_id", index)), "message": "证据映射存在未闭合缺口"}
        blockers.append(gap)
        evidence_gaps.append(gap)
    for item in value["evidence_map"]["potential_conflicts"]:
        if item.get("status") != "resolved":
            blockers.append({"code": "evidence_conflict", "target": str(item.get("conflict_id", "unknown")), "message": "证据映射存在未解决冲突"})
    for item in value["declared_conflicts"]:
        if item["status"] != "resolved":
            blockers.append({"code": "declared_conflict", "target": item["conflict_id"], "message": item["description"]})

    responses = {x["claim_id"]: x for x in value["defense_request"]["responses"]}
    matrix: list[dict[str, Any]] = []
    for claim in value["complaint"]["claims"]:
        response = responses.get(claim["claim_id"])
        if response is None:
            matrix.append({"claim_id": claim["claim_id"], "claim_text_verbatim": claim["text_verbatim"], "stance": "unanswered", "response_text": None, "fact_ids": [], "evidence_ids": [], "authority_ids": [], "provenance": {"complaint_claim": _provenance(claim), "response": None}})
            blockers.append({"code": "claim_unanswered", "target": claim["claim_id"], "message": "该诉请未收到明示答辩，不得视为承认"})
        else:
            matrix.append({"claim_id": claim["claim_id"], "claim_text_verbatim": claim["text_verbatim"], "stance": response["stance"], "response_text": response["response_text"], "fact_ids": list(response["fact_ids"]), "evidence_ids": list(response["evidence_ids"]), "authority_ids": list(response["authority_ids"]), "provenance": {"complaint_claim": _provenance(claim), "response": _provenance(response)}})
            if response["stance"] in {"deny", "procedural_objection"} and not response["evidence_ids"]:
                gap = {"code": "response_without_evidence", "target": response["response_id"], "message": "否认或程序异议未关联证据，须律师判断举证需求"}
                evidence_gaps.append(gap)
                blockers.append(gap)

    records = {x["record_id"]: x for x in value["research_report"]["records"]}
    used = {authority_id for row in matrix for authority_id in row["authority_ids"]}
    used.update(authority_id for item in value["defense_request"]["independent_defenses"] for authority_id in item["authority_ids"])
    for authority_id in sorted(used):
        record = records[authority_id]
        if record["verification_status"] != "verified" or not record["full_text_checked"] or record["effect_status"] != "effective":
            blockers.append({"code": "authority_not_verified_current", "target": authority_id, "message": "引用法源未同时满足已核验、已核对全文和现行有效"})

    return {"schema_version": "1.0", "draft_id": value["draft_id"], "matter_id": value["matter_id"], "generation_status": "blocked" if blockers else "draft_ready_for_lawyer_review", "artifact_state": "lawyer_review_required", "respondent": dict(value["defense_request"]["respondent"]), "response_matrix": matrix, "defensive_facts": [dict(x) for x in value["defense_request"]["defensive_facts"]], "independent_defenses": [dict(x) for x in value["defense_request"]["independent_defenses"]], "blockers": blockers, "evidence_gaps": evidence_gaps, "legal_notice": NOTICES}


def _provenance(item: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if item.get("source_spans"):
        result["source_spans"] = item["source_spans"]
    if item.get("user_confirmed") is True:
        result["user_confirmed"] = True
        result["confirmation_note"] = item["confirmation_note"]
    return result


def render_markdown(result: dict[str, Any]) -> str:
    labels = {"admit": "承认", "deny": "否认", "lack_knowledge": "不知悉", "procedural_objection": "程序异议", "unanswered": "未回应（不得视为承认）"}
    lines = ["# 民事答辩状（待复核结构）", "", f">产物状态：{result['generation_status']}；必须由执业律师逐案复核。", "", f"答辩人：{result['respondent']['text']}", "", "## 逐项答辩"]
    for index, row in enumerate(result["response_matrix"], 1):
        lines += [f"### {index}. {row['claim_text_verbatim']}", "", f"- 状态：{labels[row['stance']]}", f"- 答辩：{row['response_text'] or '待用户明示提供'}", ""]
    lines += ["## 独立抗辩"] + [f"- [{x['category']}] {x['text']}" for x in result["independent_defenses"]]
    lines += ["", "（不生成签名或印章）", "", "## 阻断与举证缺口"]
    lines += [f"- {x['code']}：{x['message']}（{x['target']}）" for x in result["blockers"]] or ["- 无机器阻断项，仍须律师复核。"]
    lines += ["", "## 安全声明"] + [f"- {x}" for x in result["legal_notice"]]
    return "\n".join(lines) + "\n"


def atomic_write(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖：{path}")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def build(input_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"拒绝覆盖：{output_dir}")
    value = load_json(input_path)
    validation = validate_input(value)
    if not validation["ok"]:
        raise ValueError("\n".join(validation["errors"]))
    result = derive(value)
    Draft202012Validator(schema("defense-output.schema.json")).validate(result)
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        atomic_write(output_dir / "defense.json", json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        atomic_write(output_dir / "民事答辩状-待复核.md", render_markdown(result))
        atomic_write(output_dir / "validation.json", json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    except Exception:
        for child in output_dir.iterdir(): child.unlink()
        output_dir.rmdir()
        raise
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="生成待律师复核的逐项答辩矩阵")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    build(args.input, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
