#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


LEGAL_TYPES = {"law", "administrative_regulation", "judicial_interpretation", "regulatory_document"}


def schema_errors(report: dict[str, Any], skill_root: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError:
        return ["缺少 jsonschema，无法执行结构校验"]
    schema_path = skill_root / "schemas" / "research-report.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    registry = Registry()
    for path in (skill_root / "schemas").glob("*.schema.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        schema_id = value.get("$id")
        if schema_id:
            registry = registry.with_resource(schema_id, Resource.from_contents(value))
    validator = Draft202012Validator(schema, registry=registry)
    return [f"Schema {'.'.join(str(part) for part in err.path) or '<root>'}：{err.message}" for err in validator.iter_errors(report)]


def validate(report: dict[str, Any], skill_root: Path) -> dict[str, object]:
    errors = schema_errors(report, skill_root)
    warnings: list[str] = []
    records = report.get("records", [])
    findings = report.get("findings", [])
    questions = report.get("task", {}).get("research_questions", [])

    record_ids = [record.get("record_id") for record in records]
    if len(record_ids) != len(set(record_ids)):
        errors.append("来源记录编号重复")
    record_map = {record.get("record_id"): record for record in records if record.get("record_id")}

    case_numbers: list[str] = []
    for record in records:
        record_id = record.get("record_id", "未知记录")
        if record.get("verification_status") == "verified":
            if not record.get("full_text_checked"):
                errors.append(f"{record_id} 标记为 verified 但未确认打开全文")
            if not record.get("exact_quotes"):
                errors.append(f"{record_id} 标记为 verified 但没有精确引文和定位")
        if record.get("record_type") in LEGAL_TYPES and record.get("effect_status") == "unknown":
            warnings.append(f"{record_id} 的法源效力状态尚未确认")
        number = record.get("document_number_or_case_number", "")
        if "case" in str(record.get("record_type")) or record.get("record_type") == "judgment":
            if number:
                case_numbers.append(number)
            if record.get("verification_status") == "verified" and not record.get("issuing_body_or_court"):
                errors.append(f"{record_id} 缺少法院信息")
    if len(case_numbers) != len(set(case_numbers)):
        errors.append("存在重复案号")

    question_map = {item.get("question_id"): item for item in questions}
    finding_questions: set[str] = set()
    for finding in findings:
        question_id = finding.get("question_id")
        finding_questions.add(question_id)
        if question_id not in question_map:
            errors.append(f"结论引用不存在的研究问题：{question_id}")
        for record_id in finding.get("supporting_record_ids", []):
            record = record_map.get(record_id)
            if not record:
                errors.append(f"结论引用不存在的来源：{record_id}")
                continue
            if record.get("verification_status") != "verified":
                errors.append(f"结论引用尚未核验的来源：{record_id}")
            if record.get("record_type") in LEGAL_TYPES and record.get("effect_status") not in {"effective", "not_applicable"}:
                errors.append(f"结论引用非现行或效力未明法源：{record_id}")
        question = question_map.get(question_id, {})
        if question.get("search_both_sides", True) and not finding.get("counterpoints"):
            errors.append(f"{question_id} 要求检索相反观点，但结论未记录反方观点或检索限制")
    for question_id in question_map:
        if question_id not in finding_questions:
            errors.append(f"研究问题缺少对应结论：{question_id}")

    failed_logs = [item for item in report.get("search_log", []) if item.get("status") == "failed"]
    if failed_logs and not report.get("limitations"):
        errors.append("存在失败的检索步骤，但报告没有限制说明")
    if not records:
        errors.append("报告没有任何来源记录")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def load_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("报告根节点必须是对象")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="校验中国法律检索报告的数据、来源和引用闭环")
    parser.add_argument("report", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        report = load_report(args.report)
        result = validate(report, Path(__file__).resolve().parent.parent)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = {"ok": False, "errors": [str(exc)], "warnings": []}
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
