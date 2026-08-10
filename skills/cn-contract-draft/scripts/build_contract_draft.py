#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def load_input(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(load_schema("draft-input.schema.json")).validate(value)
    return value


def finding(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def first_index(items: list[dict[str, Any]], key: str, blockers: list[dict[str, str]], path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for offset, item in enumerate(items):
        item_id = item[key]
        if item_id in result:
            blockers.append(finding("duplicate_id", f"{path}[{offset}].{key}", f"重复 ID：{item_id}"))
        else:
            result[item_id] = item
    return result


def value_conflicts(items: list[dict[str, Any]], group_key: str, value_key: str, path: str) -> list[dict[str, str]]:
    groups: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if item["confirmation_status"] == "confirmed":
            groups[item[group_key]].add(item[value_key])
    return [
        finding("confirmed_value_conflict", path, f"同一键存在不同已确认值：{key}")
        for key, values in sorted(groups.items()) if len(values) > 1
    ]


def build(value: dict[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    gaps: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    missing_refs: list[dict[str, str]] = []

    context = value["review_context"]
    if context["representation_status"] != "confirmed":
        blockers.append(finding("representation_not_confirmed", "review_context.representation_status", "代表立场未由用户确认"))
    if context["jurisdiction_status"] != "confirmed":
        blockers.append(finding("jurisdiction_not_confirmed", "review_context.jurisdiction_status", "法域未由用户确认"))

    for offset, item in enumerate(value["transaction_checklist"]):
        if item["required"] and item["status"] != "confirmed":
            gap = finding("required_checklist_item_missing", f"transaction_checklist[{offset}]", f"必需交易项未确认：{item['label']}")
            gaps.append(gap)
            blockers.append(gap.copy())
        if item["status"] == "not_applicable" and not item.get("reason", "").strip():
            gap = finding("not_applicable_without_reason", f"transaction_checklist[{offset}].reason", f"不适用项缺少理由：{item['label']}")
            gaps.append(gap)
            blockers.append(gap.copy())

    for offset, party in enumerate(value["parties"]):
        if party["confirmation_status"] != "confirmed":
            gap = finding("party_not_confirmed", f"parties[{offset}]", f"当事人角色未确认：{party['party_id']}")
            gaps.append(gap)
            blockers.append(gap.copy())

    terms = first_index(value["commercial_terms"], "term_id", blockers, "commercial_terms")
    risks = first_index(value["risk_allocations"], "risk_id", blockers, "risk_allocations")
    definitions = first_index(value["definitions"], "definition_id", blockers, "definitions")
    authorities = first_index(value["authority_records"], "record_id", blockers, "authority_records")
    first_index(value["clause_plan"], "clause_id", blockers, "clause_plan")

    conflicts.extend(value_conflicts(value["commercial_terms"], "term_key", "value", "commercial_terms"))
    conflicts.extend(value_conflicts(value["risk_allocations"], "topic", "allocation", "risk_allocations"))
    conflicts.extend(value_conflicts(value["definitions"], "term", "meaning", "definitions"))
    blockers.extend(item.copy() for item in conflicts)

    for authority_id, authority in authorities.items():
        valid = (
            authority["effect_status"] == "effective"
            and authority["verification_status"] == "verified"
            and authority["full_text_checked"] is True
            and authority["applicability_status"] == "confirmed"
        )
        if not valid:
            blockers.append(finding("authority_not_usable", f"authority_records.{authority_id}", f"法源未完成现行有效性、全文与适用性核验：{authority_id}"))

    used_definitions: set[str] = set()
    clauses: list[dict[str, Any]] = []
    lookup_specs = (
        ("term_ids", terms, "commercial_terms", "confirmation_status"),
        ("risk_ids", risks, "risk_allocations", "confirmation_status"),
        ("definition_ids", definitions, "definitions", "confirmation_status"),
        ("authority_ids", authorities, "authority_records", None),
    )
    for clause_offset, plan in enumerate(value["clause_plan"]):
        body_lines: list[str] = []
        for field, lookup, source_path, status_key in lookup_specs:
            for ref in plan[field]:
                if ref not in lookup:
                    issue = finding("missing_cross_reference", f"clause_plan[{clause_offset}].{field}", f"条款 {plan['clause_id']} 引用不存在的 {source_path} ID：{ref}")
                    missing_refs.append(issue)
                    blockers.append(issue.copy())
                elif status_key and lookup[ref][status_key] != "confirmed":
                    issue = finding("referenced_item_not_confirmed", f"clause_plan[{clause_offset}].{field}", f"条款 {plan['clause_id']} 引用未确认项：{ref}")
                    gaps.append(issue)
                    blockers.append(issue.copy())
        for ref in plan["term_ids"]:
            item = terms.get(ref)
            if item and item["confirmation_status"] == "confirmed":
                body_lines.append(f"{item['label']}：{item['value']}")
        for ref in plan["risk_ids"]:
            item = risks.get(ref)
            if item and item["confirmation_status"] == "confirmed":
                body_lines.append(f"{item['topic']}：{item['allocation']}")
        for ref in plan["definition_ids"]:
            item = definitions.get(ref)
            if item and item["confirmation_status"] == "confirmed":
                used_definitions.add(ref)
                body_lines.append(f"定义“{item['term']}”：{item['meaning']}")
        clauses.append({
            "clause_id": plan["clause_id"], "heading": plan["heading"], "body_lines": body_lines,
            "references": {key: list(plan[key]) for key in ("term_ids", "risk_ids", "definition_ids", "authority_ids")},
        })

    result = {
        "schema_version": "1.0",
        "matter_id": value["matter_id"],
        "input_sha256": hashlib.sha256(canonical_bytes(value)).hexdigest(),
        "blocked": bool(blockers),
        "blockers": blockers,
        "gaps": gaps,
        "conflicts": conflicts,
        "cross_reference_report": {
            "missing_references": missing_refs,
            "unused_definitions": sorted(set(definitions) - used_definitions),
        },
        "draft": {
            "title": value["document_title"],
            "parties": [
                {"party_id": p["party_id"], "name": p["name"], "role": p["role"]}
                for p in value["parties"] if p["confirmation_status"] == "confirmed"
            ],
            "clauses": clauses,
        },
        "authority_records": value["authority_records"],
        "artifact_state": "lawyer_review_required",
    }
    Draft202012Validator(load_schema("draft-output.schema.json")).validate(result)
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['draft']['title']}", "", "**状态：需律师审查，不得直接签署、发送或提交。**", "",
        f"案件标识：{result['matter_id']}", f"输入 SHA-256：`{result['input_sha256']}`", "",
    ]
    if result["blocked"]:
        lines.extend(["## 阻断项", ""] + [f"- {x['message']}（`{x['path']}`）" for x in result["blockers"]] + [""])
    lines.extend(["## 当事人角色", ""])
    lines.extend(f"- {p['role']}：{p['name']}（`{p['party_id']}`）" for p in result["draft"]["parties"])
    for offset, clause in enumerate(result["draft"]["clauses"], 1):
        lines.extend(["", f"## 第{offset}条 {clause['heading']}", ""])
        lines.extend(f"- {body}" for body in clause["body_lines"])
        if not clause["body_lines"]:
            lines.append("- 【待确认：该条尚无可组装的已确认内容】")
    lines.extend(["", "## 缺口与冲突", ""])
    findings = result["gaps"] + result["conflicts"] + result["cross_reference_report"]["missing_references"]
    lines.extend(f"- {x['message']}" for x in findings)
    if not findings:
        lines.append("- 未发现机器可识别的缺口或冲突；仍须律师逐项复核。")
    lines.extend(["", "---", "AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。", "使用前必须由专业执业律师人工核验事实与法律适用。", ""])
    return "\n".join(lines)


def write_pair(json_path: Path, markdown_path: Path, result: dict[str, Any]) -> None:
    if json_path == markdown_path:
        raise ValueError("两个输出路径不得相同")
    for path in (json_path, markdown_path):
        if path.exists():
            raise FileExistsError(f"拒绝覆盖：{path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    payloads = (
        (json_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n"),
        (markdown_path, render_markdown(result)),
    )
    temps: list[tuple[Path, Path]] = []
    try:
        for path, payload in payloads:
            fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temps.append((Path(name), path))
        for temp, path in temps:
            os.replace(temp, path)
    finally:
        for temp, _ in temps:
            temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="根据已确认输入生成合同工作底稿")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    if args.input in (args.json_output, args.markdown_output):
        raise ValueError("输出路径不得与输入相同")
    write_pair(args.json_output, args.markdown_output, build(load_input(args.input)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
