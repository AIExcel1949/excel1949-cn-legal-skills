#!/usr/bin/env python3
"""将法源效力、时间与适用范围分项核验，冲突解决保留律师门禁。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from verify_document import build_registry, load_json, schema_errors


ROOT = Path(__file__).resolve().parent.parent
CHECK_FIELDS = ("origin", "effect", "temporal", "geographic", "subject", "matter", "procedure")


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_assessment(verify_input: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    registry = build_registry(ROOT)
    errors = schema_errors(verify_input, ROOT / "schemas" / "verify-input.schema.json", registry)
    schema = json.loads((ROOT / "schemas" / "norm-applicability.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors.extend(
        f"Schema {'.'.join(str(part) for part in item.absolute_path) or '<root>'}：{item.message}"
        for item in sorted(validator.iter_errors(assessment), key=lambda entry: tuple(str(part) for part in entry.absolute_path))
    )
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if errors:
        return {"ok": False, "errors": errors, "blockers": blockers, "warnings": warnings, "state": "invalid"}

    if assessment["matter_id"] != verify_input["matter_id"]:
        errors.append("适用性评估与终检包的 matter_id 不一致")
    if parse_datetime(assessment["as_of"]) != parse_datetime(verify_input["review_context"]["as_of"]):
        errors.append("适用性评估与终检包的核验时点不一致")
    if errors:
        return {"ok": False, "errors": errors, "blockers": blockers, "warnings": warnings, "state": "invalid"}

    authorities = {item["record"]["authority_id"]: item for item in verify_input["authorities"]}
    norm_ids: set[str] = set()
    for norm in assessment["norms"]:
        norm_id = norm["norm_id"]
        if norm_id in norm_ids:
            errors.append(f"规范编号重复：{norm_id}")
        norm_ids.add(norm_id)
        wrapper = authorities.get(norm["authority_id"])
        if wrapper is None:
            errors.append(f"{norm_id} 引用不存在的法源：{norm['authority_id']}")
            continue
        authority = wrapper["record"]
        uncertain_fields = [field for field in CHECK_FIELDS if norm[field]["status"] == "uncertain"]
        excluded_fields = [field for field in CHECK_FIELDS if norm[field]["status"] == "not_applicable"]
        if norm["applicability_status"] == "applicable" and (uncertain_fields or excluded_fields):
            blockers.append({"code": "NORM.INCONSISTENT_APPLICABILITY", "norm_id": norm_id, "message": "存在未确认或不适用维度，不得标记为可适用。"})
        if norm["applicability_status"] == "applicable" and authority["effect_status"] not in {"effective", "amended"}:
            blockers.append({"code": "NORM.INVALID_EFFECT", "norm_id": norm_id, "message": f"法源效力状态为 {authority['effect_status']}，不得作为当前可适用依据。"})
        if norm["applicability_status"] == "applicable" and not wrapper["relied_upon"]:
            warnings.append({"code": "NORM.NOT_MARKED_RELIED", "norm_id": norm_id, "message": "评估为可适用，但终检包未将该法源标为当前依据。"})

    conflict_ids: set[str] = set()
    for conflict in assessment["conflicts"]:
        conflict_id = conflict["conflict_id"]
        if conflict_id in conflict_ids:
            errors.append(f"冲突编号重复：{conflict_id}")
        conflict_ids.add(conflict_id)
        missing = sorted(set(conflict["norm_ids"]) - norm_ids)
        if missing:
            errors.append(f"{conflict_id} 引用不存在的规范：{'、'.join(missing)}")
        if conflict["resolution_status"] == "unresolved":
            blockers.append({"code": "NORM.CONFLICT_UNRESOLVED", "norm_id": conflict_id, "message": "法源冲突尚未由律师确认解决。"})

    if assessment["fact_period"]["status"] == "unconfirmed" and any(item["applicability_status"] == "applicable" for item in assessment["norms"]):
        blockers.append({"code": "NORM.FACT_PERIOD_UNCONFIRMED", "norm_id": "fact_period", "message": "案件事实时间未确认，不得完成时间法适用结论。"})
    state = "invalid" if errors else "blocked" if blockers else "lawyer_review_required"
    return {"ok": not errors and not blockers, "errors": errors, "blockers": blockers, "warnings": warnings, "state": state}


def main() -> int:
    parser = argparse.ArgumentParser(description="校验法律规范效力、适用范围和冲突处理台账")
    parser.add_argument("verify_input", type=Path)
    parser.add_argument("assessment", type=Path)
    args = parser.parse_args()
    verify_input, _ = load_json(args.verify_input)
    assessment, _ = load_json(args.assessment)
    result = validate_assessment(verify_input, assessment)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
