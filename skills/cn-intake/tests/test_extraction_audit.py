from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("extraction_audit", ROOT / "scripts" / "audit_extraction.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def make_value() -> tuple[dict, bytes]:
    source = b"original-placeholder"
    text = "第一章 基本事实\n第1页\n第二章 争议事项\n第2页\n关键金额"
    extraction = {
        "extraction_id": "EXT-001",
        "parser_id": "PARSER-A",
        "status": "success",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "page_numbers": [1, 2],
        "section_headings": ["第一章 基本事实", "第二章 争议事项"],
        "errors": [],
    }
    value = {
        "schema_version": "1.0",
        "audit_id": "AUD-EXT-001",
        "matter_id": "MAT-EXT-001",
        "source": {"source_id": "SRC-001", "file_name": "材料.pdf", "sha256": hashlib.sha256(source).hexdigest()},
        "profile": {
            "expected_page_count": 2,
            "expected_sections": ["第一章 基本事实", "第二章 争议事项"],
            "required_anchors": ["关键金额"],
            "dual_extraction_required": False,
            "minimum_length_ratio": 0.8,
        },
        "extractions": [extraction],
        "human_review_status": "completed",
    }
    return value, source


def test_complete_extraction_passes() -> None:
    value, source = make_value()
    result = MODULE.audit(value, ROOT, source)
    assert result["status"] == "machine_checked"
    assert result["negative_inference_status"] == "human_confirmation_required"


def test_source_hash_mismatch_blocks() -> None:
    value, _ = make_value()
    result = MODULE.audit(value, ROOT, b"different")
    assert any(item["code"] == "SOURCE.HASH_MISMATCH" for item in result["findings"])


def test_text_hash_mismatch_blocks() -> None:
    value, source = make_value()
    value["extractions"][0]["text_sha256"] = "0" * 64
    result = MODULE.audit(value, ROOT, source)
    assert any(item["code"] == "EXTRACTION.HASH_MISMATCH" for item in result["findings"])


def test_missing_page_blocks() -> None:
    value, source = make_value()
    value["extractions"][0]["page_numbers"] = [1]
    result = MODULE.audit(value, ROOT, source)
    assert any(item["code"] == "EXTRACTION.PAGE_GAP" for item in result["findings"])


def test_missing_anchor_blocks() -> None:
    value, source = make_value()
    value["extractions"][0]["text"] = value["extractions"][0]["text"].replace("关键金额", "其他内容")
    value["extractions"][0]["text_sha256"] = hashlib.sha256(value["extractions"][0]["text"].encode()).hexdigest()
    result = MODULE.audit(value, ROOT, source)
    assert any(item["code"] == "EXTRACTION.ANCHOR_MISSING" for item in result["findings"])


def test_dual_path_requires_distinct_parsers() -> None:
    value, source = make_value()
    value["profile"]["dual_extraction_required"] = True
    second = json.loads(json.dumps(value["extractions"][0]))
    second["extraction_id"] = "EXT-002"
    value["extractions"].append(second)
    result = MODULE.audit(value, ROOT, source)
    assert any(item["code"] == "EXTRACTION.DUAL_PATH_MISSING" for item in result["findings"])


def test_large_length_divergence_blocks() -> None:
    value, source = make_value()
    value["profile"]["dual_extraction_required"] = True
    second = json.loads(json.dumps(value["extractions"][0]))
    second["extraction_id"] = "EXT-002"
    second["parser_id"] = "PARSER-B"
    second["text"] = "第一章 基本事实 第二章 争议事项 关键金额"
    second["text_sha256"] = hashlib.sha256(second["text"].encode()).hexdigest()
    value["extractions"].append(second)
    result = MODULE.audit(value, ROOT, source)
    assert any(item["code"] == "EXTRACTION.LENGTH_DIVERGENCE" for item in result["findings"])


def test_output_refuses_overwrite(tmp_path: Path) -> None:
    value, source = make_value()
    input_path = tmp_path / "input.json"
    source_path = tmp_path / "source.pdf"
    input_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    source_path.write_bytes(source)
    output = tmp_path / "out"
    assert MODULE.run(input_path, output, source_path) == 0
    try:
        MODULE.run(input_path, output, source_path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("应拒绝覆盖既有输出目录")
