from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from build_defense_workbench import build, derive, load_json, validate_input  # noqa: E402


@pytest.fixture
def example() -> dict:
    return load_json(SKILL_ROOT / "examples" / "criminal-defense.example.json")


def test_example_validates(example: dict) -> None:
    assert validate_input(example, SKILL_ROOT) == []


def test_output_is_fixed_to_lawyer_review_and_escalates_liberty(example: dict) -> None:
    result = derive(example)
    assert result["review_state"] == "lawyer_review_required"
    assert result["external_action_state"] == "not_performed"
    assert result["accusation_status"] == "verbatim_record_only_not_final_finding"
    assert any(item["severity"] == "critical" and "TASK-custody-001" in item["related_ids"] for item in result["human_escalations"])
    assert any("不预测刑期" in item for item in result["prohibitions"])


def test_build_writes_json_and_markdown_atomically_without_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "result"
    source = SKILL_ROOT / "examples" / "criminal-defense.example.json"
    build(source, output)
    assert sorted(item.name for item in output.iterdir()) == ["criminal-defense-workbench.json", "刑事辩护工作底稿.md"]
    data = json.loads((output / "criminal-defense-workbench.json").read_text(encoding="utf-8"))
    assert data["review_state"] == "lawyer_review_required"
    report = (output / "刑事辩护工作底稿.md").read_text(encoding="utf-8")
    assert "以下内容仅为文书原文登记" in report
    assert "不作刑期预测" in report
    before = (output / "criminal-defense-workbench.json").read_bytes()
    with pytest.raises(FileExistsError):
        build(source, output)
    assert (output / "criminal-defense-workbench.json").read_bytes() == before


def test_build_is_deterministic(tmp_path: Path) -> None:
    source = SKILL_ROOT / "examples" / "criminal-defense.example.json"
    first, second = tmp_path / "first", tmp_path / "second"
    build(source, first)
    build(source, second)
    for name in ("criminal-defense-workbench.json", "刑事辩护工作底稿.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_unofficial_authority_url_is_rejected(example: dict) -> None:
    value = copy.deepcopy(example)
    value["authorities"][0]["source_url"] = "https://example.com/law"
    errors = validate_input(value, SKILL_ROOT)
    assert any("不是中国官方机关站点" in item for item in errors)


def test_accusation_without_official_document_reference_is_rejected(example: dict) -> None:
    value = copy.deepcopy(example)
    value["accusations"][0]["source_document_ids"] = ["DOC-missing"]
    errors = validate_input(value, SKILL_ROOT)
    assert any("引用不存在的文书" in item for item in errors)


@pytest.mark.parametrize("action", ["predict_sentence", "evade_investigation", "fabricate_evidence", "contact_authority", "submit_external", "sign_or_stamp"])
def test_prohibited_actions_are_rejected(example: dict, action: str) -> None:
    value = copy.deepcopy(example)
    value["requested_actions"] = [action]
    assert any("包含禁止动作" in item for item in validate_input(value, SKILL_ROOT))


def test_deadline_rule_requires_registered_official_authority(example: dict) -> None:
    value = copy.deepcopy(example)
    value["deadline_rules"][0]["authority_ids"] = ["AUTH-missing"]
    errors = validate_input(value, SKILL_ROOT)
    assert any("期限规则" in item and "不存在的法源" in item for item in errors)
