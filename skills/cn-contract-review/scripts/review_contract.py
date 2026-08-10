#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
PROHIBITED_CERTAINTY = ("条款无效", "必然无效", "当然无效", "确定无效", "绝对无效")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def load_input(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(load_schema("review-input.schema.json")).validate(value)
    return value


def blocker(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def index_unique(items: list[dict[str, Any]], key: str, issues: list[dict[str, str]], path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for offset, item in enumerate(items):
        identity = item[key]
        if identity in result:
            issues.append(blocker("duplicate_id", f"{path}[{offset}].{key}", f"重复 ID：{identity}"))
        else:
            result[identity] = item
    return result


def read_source(path: Path, expected_hash: str) -> tuple[bytes, str]:
    raw = path.read_bytes()
    actual_hash = sha256_bytes(raw)
    if actual_hash != expected_hash:
        raise ValueError(f"源文件 SHA-256 不匹配：期望 {expected_hash}，实际 {actual_hash}")
    try:
        return raw, raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("源文件必须是 UTF-8 纯文本快照") from exc


def verify_clause_snapshot(value: dict[str, Any], source_text: str) -> None:
    source_length = len(source_text)
    for offset, clause in enumerate(value["clauses"]):
        start, end = clause["start_char"], clause["end_char"]
        if end <= start or end > source_length:
            raise ValueError(f"条款字符偏移越界：clauses[{offset}]")
        if source_text[start:end] != clause["original_text"]:
            raise ValueError(f"条款原文与源文快照不匹配：{clause['clause_id']}")


def build(value: dict[str, Any], source_raw: bytes, source_text: str) -> dict[str, Any]:
    verify_clause_snapshot(value, source_text)
    blockers: list[dict[str, str]] = []
    context = value["review_context"]
    for field, code, label in (
        ("representation_status", "representation_not_confirmed", "代表立场"),
        ("jurisdiction_status", "jurisdiction_not_confirmed", "法域"),
        ("version_status", "version_not_confirmed", "合同版本"),
    ):
        if context[field] != "confirmed":
            blockers.append(blocker(code, f"review_context.{field}", f"{label}未由用户确认"))

    clauses = index_unique(value["clauses"], "clause_id", blockers, "clauses")
    authorities = index_unique(value["authority_records"], "record_id", blockers, "authority_records")
    index_unique(value["findings"], "finding_id", blockers, "findings")
    coverage_requirements = value.get("coverage_requirements", [])
    defined_terms = value.get("defined_terms", [])
    cross_references = value.get("cross_references", [])
    index_unique(coverage_requirements, "requirement_id", blockers, "coverage_requirements")
    index_unique(defined_terms, "term_id", blockers, "defined_terms")
    index_unique(cross_references, "reference_id", blockers, "cross_references")

    for authority_id, authority in authorities.items():
        if not (
            authority["effect_status"] == "effective"
            and authority["verification_status"] == "verified"
            and authority["full_text_checked"] is True
            and authority["applicability_status"] == "confirmed"
        ):
            blockers.append(blocker("authority_not_usable", f"authority_records.{authority_id}", f"法源未完成现行有效性、全文与适用性核验：{authority_id}"))

    findings_by_clause: dict[str, list[dict[str, Any]]] = {clause_id: [] for clause_id in clauses}
    redlines: list[dict[str, Any]] = []
    for offset, item in enumerate(value["findings"]):
        path = f"findings[{offset}]"
        clause = clauses.get(item["clause_id"])
        if clause is None:
            blockers.append(blocker("unknown_clause_reference", f"{path}.clause_id", f"审查意见引用不存在的条款：{item['clause_id']}"))
            continue
        if item["clause_id"] not in item["source_refs"] and f"clause:{item['clause_id']}" not in item["source_refs"]:
            blockers.append(blocker("clause_source_missing", f"{path}.source_refs", f"审查意见未显式引用原条款：{item['clause_id']}"))
        if item["basis_type"] == "legal" and not item["authority_ids"]:
            blockers.append(blocker("legal_authority_missing", f"{path}.authority_ids", "法律类意见缺少已核验法源"))
        for authority_id in item["authority_ids"]:
            if authority_id not in authorities:
                blockers.append(blocker("unknown_authority_reference", f"{path}.authority_ids", f"引用不存在的法源：{authority_id}"))

        searchable = "\n".join((item["issue"], item["suggestion"], item["delta"]["proposed_text"]))
        for phrase in PROHIBITED_CERTAINTY:
            if phrase in searchable:
                blockers.append(blocker("invalidity_certainty_prohibited", path, f"风险提示包含未经裁判的确定无效表述：{phrase}"))
                break

        delta = item["delta"]
        operation = delta["operation"]
        target = delta["target_text"]
        proposed = delta["proposed_text"]
        if operation in {"replace", "delete", "insert_before", "insert_after"} and (not target or target not in clause["original_text"]):
            blockers.append(blocker("delta_target_not_exact", f"{path}.delta.target_text", "红线目标文本必须是原条款中逐字存在的子串"))
        if operation in {"replace", "insert_before", "insert_after"} and not proposed:
            blockers.append(blocker("delta_proposed_text_missing", f"{path}.delta.proposed_text", "替换或插入指令缺少建议文本"))
        if operation == "delete" and proposed:
            blockers.append(blocker("delete_delta_has_proposed_text", f"{path}.delta.proposed_text", "删除指令的建议文本必须留空"))
        if operation == "replace" and proposed == target:
            blockers.append(blocker("delta_has_no_change", f"{path}.delta", "替换指令的原文与建议文本相同"))

        copied = json.loads(json.dumps(item, ensure_ascii=False))
        findings_by_clause[item["clause_id"]].append(copied)
        redlines.append({
            "finding_id": item["finding_id"], "clause_id": item["clause_id"],
            "operation": operation, "target_text": target, "target_text_sha256": sha256_text(target),
            "proposed_text": proposed, "instruction_state": "not_applied",
        })

    review_items = [
        {
            "clause_id": clause["clause_id"], "heading": clause["heading"],
            "original_text": clause["original_text"], "original_text_sha256": sha256_text(clause["original_text"]),
            "findings": findings_by_clause[clause["clause_id"]],
        }
        for clause in value["clauses"]
    ]

    coverage_gaps: list[dict[str, Any]] = []
    for offset, requirement in enumerate(coverage_requirements):
        path = f"coverage_requirements[{offset}]"
        for clause_id in requirement["matched_clause_ids"]:
            if clause_id not in clauses:
                blockers.append(blocker("coverage_unknown_clause", f"{path}.matched_clause_ids", f"条款覆盖项引用不存在的条款：{clause_id}"))
        for authority_id in requirement["authority_ids"]:
            if authority_id not in authorities:
                blockers.append(blocker("coverage_unknown_authority", f"{path}.authority_ids", f"条款覆盖项引用不存在的法源：{authority_id}"))
        if requirement["basis_type"] == "legal" and requirement["applicability_status"] == "confirmed" and not requirement["authority_ids"]:
            blockers.append(blocker("coverage_legal_authority_missing", f"{path}.authority_ids", "已确认适用的法律类覆盖项缺少已核验法源"))
        gap_status = "not_applicable"
        if requirement["applicability_status"] == "unconfirmed":
            gap_status = "applicability_pending"
        elif requirement["applicability_status"] == "confirmed":
            gap_status = "covered" if requirement["matched_clause_ids"] else "missing"
        if gap_status in {"missing", "applicability_pending"}:
            coverage_gaps.append({**requirement, "gap_status": gap_status, "suggestion_state": "not_applied"})
        if gap_status == "missing" and requirement["importance"] == "blocker":
            blockers.append(blocker("coverage_blocker_missing", path, f"已确认适用的必要条款缺失：{requirement['label']}"))

    defined_term_issues: list[dict[str, Any]] = []
    normalized_terms: dict[str, str] = {}
    for offset, term in enumerate(defined_terms):
        path = f"defined_terms[{offset}]"
        normalized = "".join(term["term"].split()).casefold()
        if normalized in normalized_terms:
            blockers.append(blocker("defined_term_duplicate", f"{path}.term", f"定义词重复：{term['term']}"))
        else:
            normalized_terms[normalized] = term["term_id"]
        definition_clause_id = term["definition_clause_id"]
        if definition_clause_id is not None and definition_clause_id not in clauses:
            blockers.append(blocker("defined_term_unknown_definition_clause", f"{path}.definition_clause_id", f"定义位置引用不存在的条款：{definition_clause_id}"))
        for clause_id in term["use_clause_ids"]:
            if clause_id not in clauses:
                blockers.append(blocker("defined_term_unknown_use_clause", f"{path}.use_clause_ids", f"使用位置引用不存在的条款：{clause_id}"))
        if term["use_clause_ids"] and definition_clause_id is None:
            defined_term_issues.append({**term, "issue_type": "used_but_not_defined"})
        elif definition_clause_id is not None and not term["use_clause_ids"]:
            defined_term_issues.append({**term, "issue_type": "defined_but_not_used"})

    cross_reference_issues: list[dict[str, Any]] = []
    for offset, reference in enumerate(cross_references):
        path = f"cross_references[{offset}]"
        if reference["source_clause_id"] not in clauses:
            blockers.append(blocker("cross_reference_unknown_source", f"{path}.source_clause_id", f"交叉引用的源条款不存在：{reference['source_clause_id']}"))
        target_clause_id = reference["target_clause_id"]
        if target_clause_id is not None and target_clause_id not in clauses:
            blockers.append(blocker("cross_reference_unknown_target", f"{path}.target_clause_id", f"交叉引用的目标条款不存在：{target_clause_id}"))
        if target_clause_id is None or reference["relationship"] == "conflicts":
            cross_reference_issues.append({**reference, "issue_type": "unresolved_target" if target_clause_id is None else "declared_conflict"})

    result = {
        "schema_version": "1.0",
        "matter_id": value["matter_id"],
        "input_sha256": sha256_bytes(canonical_bytes(value)),
        "source_contract": {
            "file_name": value["source_contract"]["file_name"],
            "sha256": sha256_bytes(source_raw),
            "preserved_text_sha256": sha256_bytes(canonical_bytes([item["original_text"] for item in value["clauses"]])),
        },
        "blocked": bool(blockers),
        "blockers": blockers,
        "review_items": review_items,
        "coverage_gaps": coverage_gaps,
        "defined_term_issues": defined_term_issues,
        "cross_reference_issues": cross_reference_issues,
        "redline_instructions": redlines,
        "authority_records": value["authority_records"],
        "artifact_state": "lawyer_review_required",
    }
    Draft202012Validator(load_schema("review-output.schema.json")).validate(result)
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 合同逐条审查报告", "", "**状态：需律师审查，红线指令均未应用。**", "",
        f"案件标识：{result['matter_id']}", f"源文件 SHA-256：`{result['source_contract']['sha256']}`", "",
    ]
    if result["blocked"]:
        lines.extend(["## 阻断项", ""] + [f"- {x['message']}（`{x['path']}`）" for x in result["blockers"]] + [""])
    lines.extend(["## 条款覆盖、定义词与交叉引用", ""])
    if result["coverage_gaps"]:
        lines.extend(f"- [{x['gap_status']}/{x['importance']}] {x['label']}：{x['reason']}；建议：{x['recommendation']}（未应用）" for x in result["coverage_gaps"])
    else:
        lines.append("- 本次未登记条款覆盖缺口；不表示合同要件已齐备。")
    lines.extend(f"- [定义词/{x['issue_type']}] {x['term']}" for x in result["defined_term_issues"])
    lines.extend(f"- [交叉引用/{x['issue_type']}] {x['source_clause_id']} → {x['target_label']}" for x in result["cross_reference_issues"])
    lines.append("")
    for item in result["review_items"]:
        lines.extend([f"## {item['heading']}", "", "### 原文（逐字保留）", "", item["original_text"], "", f"原文 SHA-256：`{item['original_text_sha256']}`", ""])
        if not item["findings"]:
            lines.extend(["### 审查意见", "", "- 本次未记录问题；不表示该条款已被确认无风险。", ""])
        for finding_item in item["findings"]:
            lines.extend([
                f"### 意见 {finding_item['finding_id']}", "",
                f"- 问题：{finding_item['issue']}",
                f"- 风险：{finding_item['risk']['level']} / {finding_item['risk']['expression']}",
                f"- 来源：{'、'.join(finding_item['source_refs'])}",
                f"- 法源：{'、'.join(finding_item['authority_ids']) or '无（非法律类意见）'}",
                f"- 建议：{finding_item['suggestion']}",
                f"- 变更指令：{finding_item['delta']['operation']}（未应用）", "",
            ])
    lines.extend(["---", "AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。", "使用前必须由专业执业律师人工核验事实与法律适用。", ""])
    return "\n".join(lines)


def write_pair(json_path: Path, markdown_path: Path, result: dict[str, Any]) -> None:
    if json_path == markdown_path:
        raise ValueError("两个输出路径不得相同")
    for path in (json_path, markdown_path):
        if path.exists():
            raise FileExistsError(f"拒绝覆盖：{path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    payloads = ((json_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n"), (markdown_path, render_markdown(result)))
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
    parser = argparse.ArgumentParser(description="对 UTF-8 合同快照生成逐条审查报告")
    parser.add_argument("input", type=Path)
    parser.add_argument("--source-contract", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    if len({args.input.resolve(), args.source_contract.resolve(), args.json_output.resolve(), args.markdown_output.resolve()}) != 4:
        raise ValueError("输入、源文件和两个输出路径必须互不相同")
    value = load_input(args.input)
    raw, text = read_source(args.source_contract, value["source_contract"]["sha256"])
    write_pair(args.json_output, args.markdown_output, build(value, raw, text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
