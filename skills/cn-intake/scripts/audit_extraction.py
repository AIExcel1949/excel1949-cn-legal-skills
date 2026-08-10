#!/usr/bin/env python3
"""审计法律材料解析结果的页码、章节、锚点、哈希与双路径一致性。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("解析审计输入根节点必须是对象")
    return value


def _schema_errors(value: dict[str, Any], root: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise RuntimeError("缺少 jsonschema 依赖") from exc
    schema = _read_json(root / "schemas" / "extraction-audit.schema.json")
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
    return [f"{'.'.join(map(str, error.absolute_path)) or '<root>'}：{error.message}" for error in errors]


def _normalized_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def audit(value: dict[str, Any], root: Path, source_bytes: bytes | None = None) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def add(severity: str, code: str, location: str, message: str) -> None:
        findings.append({"severity": severity, "code": code, "location": location, "message": message})

    errors = _schema_errors(value, root)
    if errors:
        for message in errors:
            add("blocker", "SCHEMA.INVALID", "input", message)
        return _result(value, findings)

    if source_bytes is None:
        add("warning", "SOURCE.FILE_NOT_READ", "source", "本次未回读原文件，只核对了登记的 SHA-256。")
    elif hashlib.sha256(source_bytes).hexdigest() != value["source"]["sha256"]:
        add("blocker", "SOURCE.HASH_MISMATCH", "source.sha256", "原文件 SHA-256 与登记值不一致。")

    expected_pages = value["profile"]["expected_page_count"]
    expected_page_set = set(range(1, expected_pages + 1)) if expected_pages else None
    extraction_ids: set[str] = set()
    successful: list[dict[str, Any]] = []
    for offset, extraction in enumerate(value["extractions"]):
        location = f"extractions[{offset}]"
        extraction_id = extraction["extraction_id"]
        if extraction_id in extraction_ids:
            add("blocker", "EXTRACTION.DUPLICATE_ID", location, f"解析编号重复：{extraction_id}。")
        extraction_ids.add(extraction_id)
        actual_hash = hashlib.sha256(extraction["text"].encode("utf-8")).hexdigest()
        if actual_hash != extraction["text_sha256"]:
            add("blocker", "EXTRACTION.HASH_MISMATCH", location, f"解析文本 {extraction_id} 的 SHA-256 不一致。")
        if extraction["status"] != "success":
            add("blocker", "EXTRACTION.NOT_COMPLETE", location, f"解析 {extraction_id} 的状态为 {extraction['status']}。")
            continue
        if not extraction["text"].strip():
            add("blocker", "EXTRACTION.EMPTY", location, f"解析 {extraction_id} 没有可核对文本。")
            continue
        successful.append(extraction)
        if expected_page_set is not None:
            page_set = set(extraction["page_numbers"])
            missing = sorted(expected_page_set - page_set)
            extra = sorted(page_set - expected_page_set)
            if missing:
                add("blocker", "EXTRACTION.PAGE_GAP", location, f"解析 {extraction_id} 缺少页码：{missing}。")
            if extra:
                add("warning", "EXTRACTION.PAGE_OUT_OF_RANGE", location, f"解析 {extraction_id} 出现超出预期的页码：{extra}。")
        for section in value["profile"]["expected_sections"]:
            if section not in extraction["text"]:
                add("blocker", "EXTRACTION.SECTION_MISSING", location, f"解析 {extraction_id} 未找到预期章节：{section}。")
        for anchor in value["profile"]["required_anchors"]:
            if anchor not in extraction["text"]:
                add("blocker", "EXTRACTION.ANCHOR_MISSING", location, f"解析 {extraction_id} 未找到任务锚点：{anchor}。")

    if not successful:
        add("blocker", "EXTRACTION.NO_SUCCESS", "extractions", "没有完整成功的解析结果。")
    if value["profile"]["dual_extraction_required"]:
        parser_ids = {item["parser_id"] for item in successful}
        if len(parser_ids) < 2:
            add("blocker", "EXTRACTION.DUAL_PATH_MISSING", "extractions", "该材料要求双路径解析，但成功结果未覆盖两个不同 parser_id。")

    if len(successful) >= 2:
        lengths = [_normalized_length(item["text"]) for item in successful]
        longest = max(lengths)
        shortest = min(lengths)
        ratio = shortest / longest if longest else 0
        if ratio < value["profile"]["minimum_length_ratio"]:
            add("blocker", "EXTRACTION.LENGTH_DIVERGENCE", "extractions", f"成功解析的规范化字符数比例为 {ratio:.3f}，低于阈值。")
        heading_sets = [set(item["section_headings"]) for item in successful]
        if any(item != heading_sets[0] for item in heading_sets[1:]):
            add("warning", "EXTRACTION.HEADING_DIVERGENCE", "extractions", "不同解析路径识别出的章节标题不一致。")

    if value["human_review_status"] != "completed":
        add("warning", "EXTRACTION.HUMAN_REVIEW_PENDING", "human_review_status", "尚未人工打开原文件核对解析完整性。")
    return _result(value, findings)


def _result(value: dict[str, Any], findings: list[dict[str, str]]) -> dict[str, Any]:
    order = {"blocker": 0, "warning": 1, "note": 2}
    findings.sort(key=lambda item: (order[item["severity"]], item["code"], item["location"], item["message"]))
    for index, item in enumerate(findings, start=1):
        item["finding_id"] = f"EXT-{index:04d}"
    blocked = any(item["severity"] == "blocker" for item in findings)
    return {
        "schema_version": "1.0",
        "audit_id": value.get("audit_id", "invalid"),
        "matter_id": value.get("matter_id", "invalid"),
        "source_id": value.get("source", {}).get("source_id", "invalid"),
        "status": "blocked" if blocked else "machine_checked",
        "negative_inference_status": "human_confirmation_required",
        "finding_counts": {level: sum(item["severity"] == level for item in findings) for level in ("blocker", "warning", "note")},
        "findings": findings,
        "limitations": [
            "关键词未命中不能单独证明原文件没有相关内容。",
            "机器审计不能识别全部排版、附件、图片、手写批注或 OCR 语义错误。"
        ]
    }


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 材料解析完整性审计",
        "",
        f"状态：{result['status']}  ",
        f"否定性判断：{result['negative_inference_status']}",
        "",
        "## 审计发现",
        ""
    ]
    lines.extend(
        [f"- [{item['severity']}] {item['finding_id']} {item['code']}：{item['message']}" for item in result["findings"]]
        or ["- 未发现机器规则异常；仍须人工打开原文件核对。"]
    )
    lines.extend(["", "## 审计边界", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def run(input_path: Path, output_dir: Path, source_file: Path | None = None) -> int:
    if output_dir.exists():
        raise FileExistsError(f"输出目录已存在：{output_dir}")
    value = _read_json(input_path)
    source_bytes = None
    if source_file is not None:
        if source_file.is_symlink() or not source_file.is_file():
            raise ValueError("原文件必须是普通文件且不能是符号链接")
        source_bytes = source_file.read_bytes()
    root = Path(__file__).resolve().parent.parent
    result = audit(value, root, source_bytes)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-extraction-audit-", dir=output_dir.parent) as temp_name:
        temp = Path(temp_name)
        (temp / "extraction-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "extraction-audit.md").write_text(_markdown(result), encoding="utf-8")
        temp.rename(output_dir)
    return 1 if result["status"] == "blocked" else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="审计法律材料解析完整性")
    parser.add_argument("input", type=Path)
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args.input, args.output_dir, args.source_file)
    except (FileExistsError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
