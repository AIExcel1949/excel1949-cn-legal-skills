from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("citation_audit", ROOT / "scripts" / "audit_citation_ledger.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def make_value() -> dict:
    text = "依《示例法》第10条，甲方应履行约定义务。该条规定：“当事人应当依约履行。”"
    quote = "当事人应当依约履行。"
    return {
        "schema_version": "1.0",
        "matter_id": "MAT-CIT-001",
        "audit_id": "AUD-CIT-001",
        "as_of": "2026-07-23T10:00:00+08:00",
        "artifact": {
            "title": "测试文书",
            "text": text,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        },
        "authorities": [{
            "authority_id": "AUTH-001",
            "title": "示例法",
            "authority_type": "law",
            "effect_status": "effective",
            "verification_status": "verified_fulltext",
            "source_url": "https://example.gov.cn/law/1",
            "verified_at": "2026-07-23T09:00:00+08:00",
        }],
        "citations": [{
            "citation_id": "CITE-001",
            "mode": "exact_quote",
            "document_span": {"start": 0, "end": len(text), "text": text},
            "quoted_text": quote,
            "authority_refs": [{"authority_id": "AUTH-001", "locator": "第10条", "source_excerpt": quote}],
            "human_review_status": "confirmed",
        }],
    }


def test_verified_quote_passes() -> None:
    result = MODULE.audit(make_value(), ROOT)
    assert result["status"] == "machine_checked"
    assert result["finding_counts"]["blocker"] == 0


def test_hash_mismatch_blocks() -> None:
    value = make_value()
    value["artifact"]["text_sha256"] = "0" * 64
    result = MODULE.audit(value, ROOT)
    assert any(item["code"] == "ARTIFACT.HASH_MISMATCH" for item in result["findings"])


def test_span_mismatch_blocks() -> None:
    value = make_value()
    value["citations"][0]["document_span"]["text"] = "错误文本"
    result = MODULE.audit(value, ROOT)
    assert any(item["code"] == "CITATION.SPAN_MISMATCH" for item in result["findings"])


def test_quote_must_exist_in_source() -> None:
    value = make_value()
    value["citations"][0]["authority_refs"][0]["source_excerpt"] = "另一段原文"
    result = MODULE.audit(value, ROOT)
    assert any(item["code"] == "QUOTE.NOT_IN_SOURCE" for item in result["findings"])


def test_paraphrase_cannot_masquerade_as_quote() -> None:
    value = make_value()
    value["citations"][0]["mode"] = "paraphrase"
    value["citations"][0].pop("quoted_text")
    result = MODULE.audit(value, ROOT)
    assert any(item["code"] == "PARAPHRASE.PRESENTED_AS_QUOTE" for item in result["findings"])


def test_duplicate_span_blocks() -> None:
    value = make_value()
    duplicate = json.loads(json.dumps(value["citations"][0]))
    duplicate["citation_id"] = "CITE-002"
    value["citations"].append(duplicate)
    result = MODULE.audit(value, ROOT)
    assert any(item["code"] == "CITATION.DUPLICATE_SPAN" for item in result["findings"])


def test_pending_authority_blocks() -> None:
    value = make_value()
    value["authorities"][0]["verification_status"] = "pending"
    result = MODULE.audit(value, ROOT)
    assert any(item["code"] == "AUTHORITY.NOT_VERIFIED" for item in result["findings"])


def test_output_refuses_overwrite(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(make_value(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "out"
    assert MODULE.run(input_path, output) == 0
    try:
        MODULE.run(input_path, output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("应拒绝覆盖既有输出目录")
