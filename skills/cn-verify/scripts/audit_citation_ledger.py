#!/usr/bin/env python3
"""对法律文书引用台账执行只读、确定性完整性审计。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


QUOTE_AS_RULE = ("规定：“", "规定：‘")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("引用台账根节点必须是对象")
    return value


def _schema_errors(value: dict[str, Any], root: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise RuntimeError("缺少 jsonschema 依赖") from exc
    schema = _load(root / "schemas" / "citation-ledger.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
    return [f"{'.'.join(map(str, error.absolute_path)) or '<root>'}：{error.message}" for error in errors]


def audit(value: dict[str, Any], root: Path) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def add(severity: str, code: str, citation_id: str, message: str) -> None:
        findings.append({"severity": severity, "code": code, "citation_id": citation_id, "message": message})

    schema_errors = _schema_errors(value, root)
    if schema_errors:
        for message in schema_errors:
            add("blocker", "SCHEMA.INVALID", "", message)
        return _result(value, findings)

    text = value["artifact"]["text"]
    actual_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if actual_hash != value["artifact"]["text_sha256"]:
        add("blocker", "ARTIFACT.HASH_MISMATCH", "", "文书文本 SHA-256 与台账不一致。")

    authorities: dict[str, dict[str, Any]] = {}
    for authority in value["authorities"]:
        authority_id = authority["authority_id"]
        if authority_id in authorities:
            add("blocker", "AUTHORITY.DUPLICATE_ID", "", f"法源编号重复：{authority_id}。")
        authorities[authority_id] = authority

    seen_citation_ids: set[str] = set()
    seen_spans: set[tuple[int, int]] = set()
    for citation in value["citations"]:
        citation_id = citation["citation_id"]
        if citation_id in seen_citation_ids:
            add("blocker", "CITATION.DUPLICATE_ID", citation_id, "引用编号重复。")
        seen_citation_ids.add(citation_id)

        span = citation["document_span"]
        key = (span["start"], span["end"])
        if key in seen_spans:
            add("blocker", "CITATION.DUPLICATE_SPAN", citation_id, "同一文书范围存在多个引用项；共同来源应合并到一个 authority_refs 数组。")
        seen_spans.add(key)
        if span["end"] <= span["start"] or span["end"] > len(text):
            add("blocker", "CITATION.SPAN_RANGE", citation_id, "文书字符范围无效或越界。")
        elif text[span["start"]:span["end"]] != span["text"]:
            add("blocker", "CITATION.SPAN_MISMATCH", citation_id, "文书字符范围与登记文本不一致。")

        verified_excerpts: list[str] = []
        ref_ids: set[str] = set()
        for ref in citation["authority_refs"]:
            authority_id = ref["authority_id"]
            if authority_id in ref_ids:
                add("blocker", "CITATION.DUPLICATE_AUTHORITY", citation_id, f"同一引用重复登记法源 {authority_id}。")
            ref_ids.add(authority_id)
            authority = authorities.get(authority_id)
            if authority is None:
                add("blocker", "CITATION.UNKNOWN_AUTHORITY", citation_id, f"引用指向不存在的法源 {authority_id}。")
                continue
            if authority["verification_status"] != "verified_fulltext":
                add("blocker", "AUTHORITY.NOT_VERIFIED", citation_id, f"法源 {authority_id} 尚未核验全文。")
            if authority["effect_status"] in {"repealed", "not_yet_effective", "unknown"}:
                add("blocker", "AUTHORITY.INVALID_EFFECT", citation_id, f"法源 {authority_id} 的效力状态为 {authority['effect_status']}。")
            elif authority["effect_status"] == "amended":
                add("warning", "AUTHORITY.AMENDED", citation_id, f"法源 {authority_id} 已修改，须核对案件时点适用版本。")
            verified_excerpts.append(ref["source_excerpt"])

        if citation["mode"] == "exact_quote":
            quoted = citation.get("quoted_text", "")
            if quoted not in span["text"]:
                add("blocker", "QUOTE.NOT_IN_DOCUMENT_SPAN", citation_id, "逐字引文不在登记的文书范围内。")
            if not any(quoted in excerpt for excerpt in verified_excerpts):
                add("blocker", "QUOTE.NOT_IN_SOURCE", citation_id, "逐字引文未出现在任何已登记来源摘录中。")
        elif citation["mode"] == "paraphrase" and any(marker in span["text"] for marker in QUOTE_AS_RULE):
            add("blocker", "PARAPHRASE.PRESENTED_AS_QUOTE", citation_id, "转述使用了“规定：”加引号的逐字引文形式。")

        if citation["human_review_status"] != "confirmed":
            add("warning", "CITATION.HUMAN_REVIEW_PENDING", citation_id, "该引用尚未由律师打开来源全文复核。")

    return _result(value, findings)


def _result(value: dict[str, Any], findings: list[dict[str, str]]) -> dict[str, Any]:
    severity_order = {"blocker": 0, "warning": 1, "note": 2}
    findings.sort(key=lambda item: (severity_order[item["severity"]], item["code"], item["citation_id"], item["message"]))
    for index, finding in enumerate(findings, start=1):
        finding["finding_id"] = f"CIT-{index:04d}"
    blocked = any(item["severity"] == "blocker" for item in findings)
    return {
        "schema_version": "1.0",
        "matter_id": value.get("matter_id", "invalid"),
        "audit_id": value.get("audit_id", "invalid"),
        "status": "blocked" if blocked else "machine_checked",
        "finding_counts": {
            level: sum(item["severity"] == level for item in findings)
            for level in ("blocker", "warning", "note")
        },
        "findings": findings,
        "limitations": [
            "审计只覆盖台账中登记的引用，不能自动发现文书中所有未登记法律命题。",
            "机器一致性检查不能替代律师对法源效力、上下文、适用范围和法律结论的复核。"
        ]
    }


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 法律文书引用完整性审计",
        "",
        f"状态：{result['status']}  ",
        f"阻断项：{result['finding_counts']['blocker']}  ",
        f"警告项：{result['finding_counts']['warning']}",
        "",
        "## 审计发现",
        ""
    ]
    if result["findings"]:
        lines.extend(
            f"- [{item['severity']}] {item['finding_id']} {item['code']}"
            f"{'（' + item['citation_id'] + '）' if item['citation_id'] else ''}：{item['message']}"
            for item in result["findings"]
        )
    else:
        lines.append("- 未发现机器规则异常；仍须律师复核。")
    lines.extend(["", "## 审计边界", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def run(input_path: Path, output_dir: Path) -> int:
    if output_dir.exists():
        raise FileExistsError(f"输出目录已存在：{output_dir}")
    value = _load(input_path)
    root = Path(__file__).resolve().parent.parent
    result = audit(value, root)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-citation-audit-", dir=output_dir.parent) as temp_name:
        temp = Path(temp_name)
        (temp / "citation-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "citation-audit.md").write_text(_markdown(result), encoding="utf-8")
        temp.rename(output_dir)
    return 1 if result["status"] == "blocked" else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="审计法律文书引用台账")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args.input, args.output_dir)
    except (FileExistsError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
