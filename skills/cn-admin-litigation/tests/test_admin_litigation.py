from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from build_admin_workbench import build, derive, load_json, validate_input  # noqa: E402


@pytest.fixture
def example() -> dict:
    return load_json(SKILL_ROOT / "examples" / "admin-litigation.example.json")


def test_example_validates(example: dict) -> None:
    assert validate_input(example, SKILL_ROOT) == []


def test_conclusions_are_not_determined_and_claims_are_conserved(example: dict) -> None:
    result = derive(example)
    assert result["review_state"] == "lawyer_review_required"
    assert result["external_action_state"] == "not_performed"
    assert set(result["conclusion_states"].values()) == {"not_determined_by_skill"}
    assert [(item["claim_id"], item["text_verbatim"]) for item in result["claims"]] == [
        (item["claim_id"], item["text_verbatim"]) for item in example["claims"]
    ]
    assert result["claim_conservation"] == {"input_count": 1, "output_count": 1, "verbatim_preserved": True}


def test_build_writes_json_and_markdown_without_overwrite(tmp_path: Path) -> None:
    source = SKILL_ROOT / "examples" / "admin-litigation.example.json"
    output = tmp_path / "result"
    build(source, output)
    assert sorted(item.name for item in output.iterdir()) == ["admin-litigation-workbench.json", "行政诉讼工作底稿.md"]
    data = json.loads((output / "admin-litigation-workbench.json").read_text(encoding="utf-8"))
    assert data["review_state"] == "lawyer_review_required"
    report = (output / "行政诉讼工作底稿.md").read_text(encoding="utf-8")
    assert "脚本不计算或认定起诉期限" in report
    assert "请求依法撤销被诉行政行为" in report
    before = (output / "admin-litigation-workbench.json").read_bytes()
    with pytest.raises(FileExistsError):
        build(source, output)
    assert (output / "admin-litigation-workbench.json").read_bytes() == before


def test_build_is_deterministic(tmp_path: Path) -> None:
    source = SKILL_ROOT / "examples" / "admin-litigation.example.json"
    first, second = tmp_path / "first", tmp_path / "second"
    build(source, first)
    build(source, second)
    for name in ("admin-litigation-workbench.json", "行政诉讼工作底稿.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_unofficial_authority_url_is_rejected(example: dict) -> None:
    value = copy.deepcopy(example)
    value["authorities"][0]["source_url"] = "https://example.com/admin-law"
    assert any("不是中国官方机关站点" in item for item in validate_input(value, SKILL_ROOT))


def test_deadline_must_reference_existing_event_and_authority(example: dict) -> None:
    value = copy.deepcopy(example)
    value["filing_deadline_rules"][0]["start_event_ids"] = ["EVENT-missing"]
    value["filing_deadline_rules"][0]["authority_ids"] = ["AUTH-missing"]
    errors = validate_input(value, SKILL_ROOT)
    assert any("不存在的起算事件" in item for item in errors)
    assert any("不存在的法源" in item for item in errors)


def test_service_gap_and_deadline_gap_are_escalated(example: dict) -> None:
    result = derive(example)
    related = {related for item in result["human_escalations"] for related in item["related_ids"]}
    assert "SERVICE-001" in related
    assert "RULE-filing-001" in related


@pytest.mark.parametrize("action", ["determine_actionability", "determine_jurisdiction", "determine_reconsideration_precondition", "calculate_or_determine_deadline", "contact_or_submit_external", "sign_or_stamp"])
def test_prohibited_actions_are_rejected(example: dict, action: str) -> None:
    value = copy.deepcopy(example)
    value["requested_actions"] = [action]
    assert any("包含禁止动作" in item for item in validate_input(value, SKILL_ROOT))


def test_claim_target_must_be_the_recorded_administrative_act(example: dict) -> None:
    value = copy.deepcopy(example)
    value["claims"][0]["target_act_id"] = "ACT-missing"
    assert any("指向不存在的行政行为" in item for item in validate_input(value, SKILL_ROOT))
