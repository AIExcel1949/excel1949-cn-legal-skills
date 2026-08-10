from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("contract_review", SKILL / "scripts" / "review_contract.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


@pytest.fixture
def materials():
    value = json.loads((SKILL / "examples" / "review-input.example.json").read_text(encoding="utf-8"))
    raw = (SKILL / "examples" / "contract-snapshot.example.txt").read_bytes()
    return value, raw, raw.decode("utf-8")


def codes(result):
    return {item["code"] for item in result["blockers"]}


def test_example_matches_input_schema(materials):
    value, _, _ = materials
    Draft202012Validator(module.load_schema("review-input.schema.json")).validate(value)


def test_valid_review_preserves_exact_text_and_hash(materials):
    value, raw, text = materials
    result = module.build(value, raw, text)
    assert result["blocked"] is False
    assert result["review_items"][0]["original_text"] == value["clauses"][0]["original_text"]
    assert result["review_items"][0]["original_text_sha256"] == module.sha256_text(value["clauses"][0]["original_text"])
    assert result["artifact_state"] == "lawyer_review_required"
    Draft202012Validator(module.load_schema("review-output.schema.json")).validate(result)


def test_redline_is_not_applied_to_original(materials):
    value, raw, text = materials
    before = value["clauses"][1]["original_text"]
    result = module.build(value, raw, text)
    assert result["review_items"][1]["original_text"] == before
    assert result["redline_instructions"][1]["instruction_state"] == "not_applied"
    assert result["redline_instructions"][1]["proposed_text"] not in result["review_items"][1]["original_text"]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("representation_status", "representation_not_confirmed"),
        ("jurisdiction_status", "jurisdiction_not_confirmed"),
        ("version_status", "version_not_confirmed"),
    ],
)
def test_unconfirmed_review_context_blocks(materials, field, expected):
    value, raw, text = materials
    value["review_context"][field] = "unconfirmed"
    assert expected in codes(module.build(value, raw, text))


def test_stale_authority_blocks(materials):
    value, raw, text = materials
    value["authority_records"][0]["effect_status"] = "repealed"
    assert "authority_not_usable" in codes(module.build(value, raw, text))


def test_legal_finding_without_authority_blocks(materials):
    value, raw, text = materials
    value["findings"][0]["basis_type"] = "legal"
    assert "legal_authority_missing" in codes(module.build(value, raw, text))


def test_invalidity_certainty_is_blocked(materials):
    value, raw, text = materials
    value["findings"][0]["issue"] = "本条款无效。"
    assert "invalidity_certainty_prohibited" in codes(module.build(value, raw, text))


def test_non_exact_delta_target_blocks(materials):
    value, raw, text = materials
    value["findings"][1]["delta"]["target_text"] = "原文中不存在的目标"
    assert "delta_target_not_exact" in codes(module.build(value, raw, text))


def test_source_hash_mismatch_fails_closed(materials, tmp_path):
    value, _, _ = materials
    path = tmp_path / "contract.txt"
    path.write_text("被改变的源文本", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        module.read_source(path, value["source_contract"]["sha256"])


def test_clause_offset_mismatch_fails_closed(materials):
    value, raw, text = materials
    value["clauses"][0]["original_text"] += "新增"
    with pytest.raises(ValueError, match="不匹配"):
        module.build(value, raw, text)


def test_output_is_deterministic(materials):
    value, raw, text = materials
    assert module.build(value, raw, text) == module.build(copy.deepcopy(value), raw, text)


def test_write_pair_refuses_overwrite(materials, tmp_path):
    value, raw, text = materials
    result = module.build(value, raw, text)
    json_path, md_path = tmp_path / "review.json", tmp_path / "review.md"
    md_path.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        module.write_pair(json_path, md_path, result)
    assert not json_path.exists()
    assert md_path.read_text(encoding="utf-8") == "keep"


def test_write_pair_outputs_separated_sections(materials, tmp_path):
    value, raw, text = materials
    result = module.build(value, raw, text)
    json_path, md_path = tmp_path / "review.json", tmp_path / "review.md"
    module.write_pair(json_path, md_path, result)
    stored = json.loads(json_path.read_text(encoding="utf-8"))
    assert stored["review_items"][0]["findings"][0]["suggestion"]
    assert stored["redline_instructions"][0]["instruction_state"] == "not_applied"
    assert "逐字保留" in md_path.read_text(encoding="utf-8")


def test_confirmed_missing_coverage_is_reported_without_applying_text(materials):
    value, raw, text = materials
    value["coverage_requirements"] = [{
        "requirement_id": "REQ-001", "label": "验收标准",
        "applicability_status": "confirmed", "importance": "high", "basis_type": "commercial",
        "reason": "履行标准需由当事人确认。", "matched_clause_ids": [], "authority_ids": [],
        "recommendation": "请律师结合交易文件起草验收条款。",
    }]
    result = module.build(value, raw, text)
    assert result["coverage_gaps"][0]["gap_status"] == "missing"
    assert result["coverage_gaps"][0]["suggestion_state"] == "not_applied"
    assert result["blocked"] is False


def test_blocker_coverage_gap_stops_delivery(materials):
    value, raw, text = materials
    value["coverage_requirements"] = [{
        "requirement_id": "REQ-002", "label": "当事人明示要求的终止权",
        "applicability_status": "confirmed", "importance": "blocker", "basis_type": "commercial",
        "reason": "已经客户明示确认。", "matched_clause_ids": [], "authority_ids": [],
        "recommendation": "由律师确认触发条件与法律后果。",
    }]
    assert "coverage_blocker_missing" in codes(module.build(value, raw, text))


def test_legal_coverage_requires_verified_authority_reference(materials):
    value, raw, text = materials
    value["coverage_requirements"] = [{
        "requirement_id": "REQ-003", "label": "法律强制性事项",
        "applicability_status": "confirmed", "importance": "high", "basis_type": "legal",
        "reason": "根据已确认的交易类型纳入。", "matched_clause_ids": [], "authority_ids": [],
        "recommendation": "先核验现行法源，再由律师起草。",
    }]
    assert "coverage_legal_authority_missing" in codes(module.build(value, raw, text))


def test_defined_term_and_cross_reference_issues_are_auditable(materials):
    value, raw, text = materials
    clause_id = value["clauses"][0]["clause_id"]
    value["defined_terms"] = [{
        "term_id": "TERM-001", "term": "交付物", "definition_clause_id": None,
        "use_clause_ids": [clause_id], "review_status": "confirmed",
    }]
    value["cross_references"] = [{
        "reference_id": "XREF-001", "source_clause_id": clause_id,
        "target_clause_id": None, "target_label": "附件二",
        "relationship": "incorporates", "review_status": "confirmed",
    }]
    result = module.build(value, raw, text)
    assert result["defined_term_issues"][0]["issue_type"] == "used_but_not_defined"
    assert result["cross_reference_issues"][0]["issue_type"] == "unresolved_target"


def test_declared_registry_references_must_resolve(materials):
    value, raw, text = materials
    value["defined_terms"] = [{
        "term_id": "TERM-002", "term": "服务期", "definition_clause_id": "CLAUSE-NOT-FOUND",
        "use_clause_ids": [], "review_status": "ai_proposed",
    }]
    assert "defined_term_unknown_definition_clause" in codes(module.build(value, raw, text))
