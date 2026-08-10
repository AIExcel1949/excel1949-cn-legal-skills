#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SKILL_ROOT = Path(__file__).resolve().parent.parent
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


def _schema(name: str) -> dict[str, Any]:
    return load_json(SKILL_ROOT / "schemas" / name)


def validate_input(value: dict[str, Any]) -> dict[str, Any]:
    validator = Draft202012Validator(_schema("complaint-input.schema.json"), format_checker=FormatChecker())
    errors = [f"{'.'.join(str(x) for x in e.absolute_path) or '$'}: {e.message}" for e in sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path))]
    if errors:
        return {"ok": False, "errors": errors}

    ids: dict[str, list[str]] = {
        "party_id": [x["party_id"] for x in value["draft_request"]["parties"]],
        "claim_id": [x["claim_id"] for x in value["draft_request"]["claims"]],
        "fact_id": [x["fact_id"] for x in value["draft_request"]["facts"]],
        "ground_id": [x["ground_id"] for x in value["draft_request"]["legal_grounds"]],
    }
    for label, values in ids.items():
        if len(values) != len(set(values)):
            errors.append(f"{label} 存在重复值")

    matter_id = value["matter_id"]
    for key in ("case_analysis", "evidence_map"):
        if value[key]["matter_id"] != matter_id:
            errors.append(f"{key}.matter_id 与顶层 matter_id 不一致")
    if value["research_report"]["task"]["matter_id"] != matter_id:
        errors.append("research_report.task.matter_id 与顶层 matter_id 不一致")

    evidence_ids = {str(item.get("evidence_id")) for item in value["evidence_map"]["matrix"] if item.get("evidence_id")}
    for evidence_id in value["draft_request"]["evidence_ids"]:
        if evidence_id not in evidence_ids:
            errors.append(f"证据 {evidence_id} 不在 evidence_map.matrix 中")
    for fact in value["draft_request"]["facts"]:
        for evidence_id in fact.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                errors.append(f"事实 {fact['fact_id']} 引用不存在的证据 {evidence_id}")

    authority_ids = {x["record_id"] for x in value["research_report"]["records"]}
    for ground in value["draft_request"]["legal_grounds"]:
        for authority_id in ground["authority_ids"]:
            if authority_id not in authority_ids:
                errors.append(f"理由 {ground['ground_id']} 引用不存在的法源 {authority_id}")

    calculation_ids = {str(x.get("id")) for x in value.get("calculation_report", {}).get("calculations", []) if x.get("id")}
    for claim in value["draft_request"]["claims"]:
        if claim.get("calculation_id") and claim["calculation_id"] not in calculation_ids:
            errors.append(f"诉请 {claim['claim_id']} 引用不存在的计算结果 {claim['calculation_id']}")
    return {"ok": not errors, "errors": errors}


def _blockers(value: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    blockers: list[dict[str, str]] = []
    gaps: list[dict[str, str]] = []
    for index, item in enumerate(value["case_analysis"]["pending_confirmations"], 1):
        blockers.append({"code": "pending_confirmation", "target": str(item.get("confirmation_id", index)), "message": "案件分析存在待确认事项"})
    for index, item in enumerate(value["evidence_map"]["gaps"], 1):
        target = str(item.get("target_id", index))
        gap = {"code": str(item.get("gap_type", "evidence_gap")), "target": target, "message": "证据映射存在未闭合缺口"}
        gaps.append(gap)
        blockers.append(gap)
    for item in value["evidence_map"]["potential_conflicts"]:
        if item.get("status") != "resolved":
            blockers.append({"code": "evidence_conflict", "target": str(item.get("conflict_id", "unknown")), "message": "证据映射存在未解决冲突"})
    for item in value["declared_conflicts"]:
        if item["status"] != "resolved":
            blockers.append({"code": "declared_conflict", "target": item["conflict_id"], "message": item["description"]})

    records = {x["record_id"]: x for x in value["research_report"]["records"]}
    used = {authority_id for ground in value["draft_request"]["legal_grounds"] for authority_id in ground["authority_ids"]}
    for authority_id in sorted(used):
        record = records[authority_id]
        if record["verification_status"] != "verified" or not record["full_text_checked"] or record["effect_status"] != "effective":
            blockers.append({"code": "authority_not_verified_current", "target": authority_id, "message": "引用法源未同时满足已核验、已核对全文和现行有效"})
    report = value.get("calculation_report")
    if report and not report["lawyer_reviewed"]:
        for claim in value["draft_request"]["claims"]:
            if claim.get("calculation_id"):
                blockers.append({"code": "calculation_unreviewed", "target": claim["claim_id"], "message": "诉请引用的计算结果未经律师复核"})
    return blockers, gaps


def derive(value: dict[str, Any]) -> dict[str, Any]:
    request = value["draft_request"]
    claims = [dict(item) for item in request["claims"]]
    audit_items = []
    for index, claim in enumerate(claims):
        digest = hashlib.sha256(claim["text_verbatim"].encode("utf-8")).hexdigest()
        audit_items.append({"claim_id": claim["claim_id"], "input_index": index, "output_index": index, "input_text_sha256": digest, "output_text_sha256": digest, "exact_match": True})
    blockers, gaps = _blockers(value)
    return {
        "schema_version": "1.0", "draft_id": value["draft_id"], "matter_id": value["matter_id"],
        "generation_status": "blocked" if blockers else "draft_ready_for_lawyer_review",
        "artifact_state": "lawyer_review_required",
        "complaint": {"title": "民事起诉状", "court": dict(request["court"]), "case_type": dict(request["case_type"]), "parties": [dict(x) for x in request["parties"]], "claims": claims, "facts": [dict(x) for x in request["facts"]], "legal_grounds": [dict(x) for x in request["legal_grounds"]], "evidence_ids": list(request["evidence_ids"])},
        "claim_conservation_audit": {"input_count": len(claims), "output_count": len(claims), "order_preserved": True, "all_exact": True, "items": audit_items},
        "blockers": blockers, "gaps": gaps, "legal_notice": NOTICES,
    }


def render_markdown(result: dict[str, Any]) -> str:
    doc = result["complaint"]
    lines = ["# 民事起诉状", "", f">产物状态：{result['generation_status']}；必须由执业律师逐案复核。", "", "## 当事人"]
    lines += [f"- {x['role']}：{x['display_text']}" for x in doc["parties"]]
    lines += ["", "## 诉讼请求"] + [f"{i}. {x['text_verbatim']}" for i, x in enumerate(doc["claims"], 1)]
    lines += ["", "## 事实"] + [f"- [{x['fact_id']}] {x['text']}" for x in doc["facts"]]
    lines += ["", "## 理由"] + [f"- [{x['ground_id']}] {x['text']}" for x in doc["legal_grounds"]]
    lines += ["", f"此致  {doc['court']['text']}", "", "（不生成签名或印章）", "", "## 阻断与缺口"]
    lines += [f"- {x['code']}：{x['message']}（{x['target']}）" for x in result["blockers"]] or ["- 无机器阻断项，仍须律师复核。"]
    lines += ["", "## 安全声明"] + [f"- {x}" for x in result["legal_notice"]]
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def build(input_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"拒绝覆盖：{output_dir}")
    value = load_json(input_path)
    validation = validate_input(value)
    if not validation["ok"]:
        raise ValueError("\n".join(validation["errors"]))
    result = derive(value)
    output_validator = Draft202012Validator(_schema("complaint-output.schema.json"))
    output_validator.validate(result)
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        _atomic_write(output_dir / "complaint.json", json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        _atomic_write(output_dir / "民事起诉状-待复核.md", render_markdown(result))
        _atomic_write(output_dir / "validation.json", json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    except Exception:
        for child in output_dir.iterdir():
            child.unlink()
        output_dir.rmdir()
        raise
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="生成待律师复核的民事起诉状结构")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    build(args.input, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
