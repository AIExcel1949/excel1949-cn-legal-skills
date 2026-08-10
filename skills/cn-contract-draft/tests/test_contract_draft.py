from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("contract_draft", SKILL / "scripts" / "build_contract_draft.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


@pytest.fixture
def valid_input():
    return json.loads((SKILL / "examples" / "draft-input.example.json").read_text(encoding="utf-8"))


def codes(result):
    return {item["code"] for item in result["blockers"]}


def test_example_matches_input_schema(valid_input):
    Draft202012Validator(module.load_schema("draft-input.schema.json")).validate(valid_input)


def test_valid_build_has_fixed_review_state(valid_input):
    result = module.build(valid_input)
    assert result["blocked"] is False
    assert result["artifact_state"] == "lawyer_review_required"
    Draft202012Validator(module.load_schema("draft-output.schema.json")).validate(result)


def test_draft_only_assembles_confirmed_values(valid_input):
    result = module.build(valid_input)
    lines = result["draft"]["clauses"][0]["body_lines"]
    assert lines == [
        "服务内容：乙公司为甲公司提供系统维护服务",
        "系统访问权限：甲公司按已确认人员名单开通最小必要权限",
        "定义“系统”：甲公司在附件一列明的业务系统",
    ]


def test_required_checklist_gap_blocks(valid_input):
    value = copy.deepcopy(valid_input)
    value["transaction_checklist"][0]["status"] = "missing"
    result = module.build(value)
    assert "required_checklist_item_missing" in codes(result)
    assert result["blocked"] is True


def test_confirmed_business_term_conflict_is_visible(valid_input):
    value = copy.deepcopy(valid_input)
    duplicate = copy.deepcopy(value["commercial_terms"][0])
    duplicate.update(term_id="TERM-SCOPE-ALT", value="乙公司提供全部信息系统服务")
    value["commercial_terms"].append(duplicate)
    result = module.build(value)
    assert "confirmed_value_conflict" in codes(result)
    assert result["conflicts"]


def test_missing_cross_reference_blocks_without_invention(valid_input):
    value = copy.deepcopy(valid_input)
    value["clause_plan"][0]["term_ids"].append("TERM-UNKNOWN")
    result = module.build(value)
    assert "missing_cross_reference" in codes(result)
    assert all("TERM-UNKNOWN" not in line for line in result["draft"]["clauses"][0]["body_lines"])


def test_unverified_authority_blocks(valid_input):
    value = copy.deepcopy(valid_input)
    value["authority_records"][0]["verification_status"] = "pending"
    result = module.build(value)
    assert "authority_not_usable" in codes(result)


def test_output_is_deterministic(valid_input):
    assert module.build(valid_input) == module.build(copy.deepcopy(valid_input))


def test_write_pair_refuses_overwrite(valid_input, tmp_path):
    result = module.build(valid_input)
    json_path, md_path = tmp_path / "draft.json", tmp_path / "draft.md"
    json_path.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        module.write_pair(json_path, md_path, result)
    assert json_path.read_text(encoding="utf-8") == "keep"
    assert not md_path.exists()


def test_write_pair_creates_both_outputs(valid_input, tmp_path):
    result = module.build(valid_input)
    json_path, md_path = tmp_path / "draft.json", tmp_path / "draft.md"
    module.write_pair(json_path, md_path, result)
    assert json.loads(json_path.read_text(encoding="utf-8"))["artifact_state"] == "lawyer_review_required"
    assert "需律师审查" in md_path.read_text(encoding="utf-8")

