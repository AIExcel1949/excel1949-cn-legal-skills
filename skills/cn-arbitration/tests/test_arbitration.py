from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from build_arbitration import InputError, build_workbench, load_input, render_markdown, write_pair_atomic  # noqa: E402


EXAMPLE = SKILL_DIR / "examples" / "arbitration-input.example.json"


def example():
    return load_input(EXAMPLE)


def raw_for(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")


def test_example_is_deterministic_schema_valid_and_review_required():
    data, raw = example()
    first = build_workbench(data, raw)
    second = build_workbench(data, raw)
    assert first == second
    assert first["artifact_state"] == "lawyer_review_required"
    assert first["action_controls"]["auto_select_institution"] is False
    assert first["action_controls"]["auto_select_arbitrator"] is False
    assert first["action_controls"]["auto_calculate_deadlines"] is False
    schema = json.loads((SKILL_DIR / "schemas" / "arbitration-output.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(first)


def test_pending_agreement_and_conflict_are_blocked_without_validity_decision():
    data, _ = example()
    data = copy.deepcopy(data)
    data["arbitration_agreement"]["review_status"] = "pending"
    data["arbitration_agreement"]["conflicts"] = ["两份合同的机构名称不一致"]
    result = build_workbench(data, raw_for(data))
    assert result["agreement_review"]["validity_decision"] is None
    assert len(result["agreement_review"]["blockers"]) == 2


def test_institution_is_never_auto_selected():
    data, _ = example()
    data = copy.deepcopy(data)
    data["institution"]["selection_status"] = "pending"
    result = build_workbench(data, raw_for(data))
    assert result["institution_review"]["selected_by_script"] is False
    assert any("不代为选择" in item for item in result["blockers"])


def test_rule_unknown_or_future_verification_is_blocked():
    data, _ = example()
    data = copy.deepcopy(data)
    data["authorities"][0]["effect_status"] = "unknown"
    data["authorities"][0]["verified_on"] = "2026-07-19"
    result = build_workbench(data, raw_for(data))
    assert len(result["authority_review"][0]["blockers"]) == 2


def test_claim_missing_evidence_and_authority_links_is_blocked():
    data, _ = example()
    data = copy.deepcopy(data)
    data["claims"][0]["evidence_ids"] = []
    data["claims"][0]["authority_ids"] = ["RULE-NOT-REGISTERED"]
    result = build_workbench(data, raw_for(data))
    blockers = result["claim_register"][0]["blockers"]
    assert any("证据引用" in item for item in blockers)
    assert any("依据引用" in item for item in blockers)


def test_pending_arbitrator_disclosure_has_no_auto_recommendation():
    data, _ = example()
    data = copy.deepcopy(data)
    data["arbitrator_disclosures"][0]["assessment_status"] = "pending"
    data["arbitrator_disclosures"][0]["response_plan"] = ""
    result = build_workbench(data, raw_for(data))
    disclosure = result["disclosure_register"][0]
    assert disclosure["automatic_recommendation"] is None
    assert len(disclosure["blockers"]) == 2


def test_schedule_missing_date_is_not_calculated():
    data, _ = example()
    data = copy.deepcopy(data)
    data["schedule"][0]["date"] = None
    data["schedule"][0]["date_basis"] = ""
    result = build_workbench(data, raw_for(data))
    schedule = result["schedule_register"][0]
    assert schedule["calculated_by_script"] is False
    assert any("不自动计算" in item for item in schedule["blockers"])


def test_schedule_unknown_source_is_blocked():
    data, _ = example()
    data = copy.deepcopy(data)
    data["schedule"][1]["source_ref"] = "RULE-NOT-REGISTERED"
    result = build_workbench(data, raw_for(data))
    assert any("无法对应" in item for item in result["schedule_register"][1]["blockers"])


def test_atomic_pair_refuses_overwrite(tmp_path: Path):
    json_path = tmp_path / "workbench.json"
    md_path = tmp_path / "workbench.md"
    md_path.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        write_pair_atomic(json_path, b"json", md_path, b"markdown")
    assert not json_path.exists()
    assert md_path.read_text(encoding="utf-8") == "keep"


def test_duplicate_json_key_is_rejected(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
    with pytest.raises(InputError, match="重复 JSON 键"):
        load_input(path)


def test_markdown_states_all_automatic_prohibitions():
    data, raw = example()
    text = render_markdown(build_workbench(data, raw))
    assert "不自动选机构" in text
    assert "选仲裁员" in text
    assert "计算期限" in text
    assert "发送" in text
