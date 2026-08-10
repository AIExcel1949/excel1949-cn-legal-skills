from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "enforcement.example.json"


def module():
    spec = importlib.util.spec_from_file_location("build_enforcement_review_test", ROOT / "scripts" / "build_enforcement_review.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sample():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_builds_two_artifacts_and_refuses_overwrite(tmp_path: Path):
    tool = module()
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(sample(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "result"
    tool.build(input_path, output)
    assert {item.name for item in output.iterdir()} == {"enforcement-review.json", "执行申请审查工作底稿.md"}
    result = json.loads((output / "enforcement-review.json").read_text(encoding="utf-8"))
    assert result["artifact_state"] == "lawyer_review_required"
    with pytest.raises(FileExistsError):
        tool.build(input_path, output)


def test_amount_is_referenced_without_recalculation():
    tool = module()
    value = sample()
    result = tool.derive(value)
    amount = result["amount_bypass_audit"][0]
    assert amount["display_value"] == value["amount_references"][0]["display_value"]
    assert amount["recalculated"] is False


def test_property_information_remains_only_a_clue():
    tool = module()
    value = sample()
    value["property_clues"][0]["reported_verification_status"] = "officially_confirmed"
    clue = tool.derive(value)["property_clue_audit"][0]
    assert clue["classification"] == "clue_only_not_confirmed_property"
    assert clue["status"] == "lawyer_review_required"


def test_unverified_effect_cannot_have_conclusion():
    tool = module()
    value = sample()
    value["execution_basis"]["effect_review"]["conclusion"] = "已生效"
    assert any("效力未核验" in item for item in tool.validate(value, ROOT))


def test_obligation_must_reference_registered_party():
    tool = module()
    value = sample()
    value["execution_basis"]["obligations"][0]["debtor_party_id"] = "PTY-MISSING"
    assert any("不存在主体" in item for item in tool.validate(value, ROOT))


def test_procedure_rule_must_reference_registered_authority():
    tool = module()
    value = sample()
    value["procedure_nodes"][0]["rule_inputs"][0]["authority_id"] = "AUTH-MISSING"
    assert any("不存在法源" in item for item in tool.validate(value, ROOT))


def test_external_control_action_is_blocked_and_measure_not_performed():
    tool = module()
    value = sample()
    value["external_action_requested"] = True
    assert any("禁止自动查控" in item for item in tool.validate(value, ROOT))
    clean = sample()
    assert tool.derive(clean)["measure_candidate_audit"][0]["external_action_performed"] is False
