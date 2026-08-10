from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from build_analysis import build, derive  # noqa: E402
from validate_analysis import atomic_write_json, load_json, validate  # noqa: E402


@pytest.fixture
def example() -> dict:
    return load_json(SKILL_ROOT / "examples" / "case-analysis.example.json")


def test_example_validates_against_core_contracts(example: dict) -> None:
    result = validate(example, SKILL_ROOT)
    assert result["ok"] is True
    assert result["errors"] == []


def test_derived_output_is_neutral_and_covers_three_frames(example: dict) -> None:
    result = derive(example)
    assert result["cause_of_action_status"] == "not_selected_by_skill"
    assert result["final_outcome_status"] == "lawyer_independent_judgment_required"
    assert result["frame_coverage"] == {"claim_right": True, "defense": True, "procedure": True}
    assert {item["issue_id"] for item in result["element_matrix"]} == {
        "ISSUE-payment",
        "ISSUE-quality-defense",
        "ISSUE-jurisdiction",
    }
    assert any(item["research_id"] == "AUTO-RESEARCH-ELEMENT-notice" for item in result["research_items"])
    assert any(item["confirmation_id"] == "AUTO-CONFIRM-FACT-quality-notice" for item in result["pending_confirmations"])


def test_build_writes_atomic_non_overwriting_report(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    build(SKILL_ROOT / "examples" / "case-analysis.example.json", output)
    assert sorted(path.name for path in output.iterdir()) == [
        "analysis-derived.json",
        "analysis.normalized.json",
        "validation.json",
        "案件中立分析报告.md",
    ]
    report = (output / "案件中立分析报告.md").read_text(encoding="utf-8")
    for heading in ("事实记录", "争议事实与对立主张", "证据记录", "法源记录", "待确认事项", "律师独立判断区"):
        assert heading in report
    assert "案由：未由本 Skill 自动选择" in report
    assert "最终结论：待律师独立判断" in report
    assert "分析框架覆盖：请求权=已建立；抗辩=已建立；程序=已建立" in report
    original = (output / "analysis-derived.json").read_bytes()
    with pytest.raises(FileExistsError):
        build(SKILL_ROOT / "examples" / "case-analysis.example.json", output)
    assert (output / "analysis-derived.json").read_bytes() == original


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    source = SKILL_ROOT / "examples" / "case-analysis.example.json"
    build(source, first)
    build(source, second)
    for name in ("analysis-derived.json", "analysis.normalized.json", "validation.json", "案件中立分析报告.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_dangling_reference_is_rejected(example: dict) -> None:
    value = copy.deepcopy(example)
    value["issue_analyses"][0]["elements"][0]["evidence_ids"] = ["EVID-not-exist"]
    result = validate(value, SKILL_ROOT)
    assert result["ok"] is False
    assert any("不存在的证据" in error for error in result["errors"])


def test_issue_cycle_is_rejected(example: dict) -> None:
    value = copy.deepcopy(example)
    value["issue_analyses"][0]["parent_issue_id"] = "ISSUE-quality-defense"
    result = validate(value, SKILL_ROOT)
    assert result["ok"] is False
    assert "争点树存在环" in result["errors"]


def test_analysis_must_match_every_core_issue(example: dict) -> None:
    value = copy.deepcopy(example)
    value["issue_analyses"].pop()
    result = validate(value, SKILL_ROOT)
    assert result["ok"] is False
    assert any("争点缺少分析节点" in error for error in result["errors"])


def test_missing_frame_is_explicit_warning(example: dict) -> None:
    value = copy.deepcopy(example)
    value["issues"] = [item for item in value["issues"] if item["issue_id"] != "ISSUE-jurisdiction"]
    value["issue_analyses"] = [item for item in value["issue_analyses"] if item["issue_id"] != "ISSUE-jurisdiction"]
    result = validate(value, SKILL_ROOT)
    assert result["ok"] is True
    assert any("程序分析节点" in warning for warning in result["warnings"])


def test_provided_lawyer_judgment_requires_review_metadata(example: dict) -> None:
    value = copy.deepcopy(example)
    value["lawyer_judgments"][0]["status"] = "provided"
    value["lawyer_judgments"][0]["content"] = "待复核的律师意见。"
    result = validate(value, SKILL_ROOT)
    assert result["ok"] is False
    assert any("reviewed_by" in error or "reviewed_at" in error for error in result["errors"])


def test_validation_report_is_atomic_and_non_overwriting(example: dict, tmp_path: Path) -> None:
    report = tmp_path / "validation.json"
    result = validate(example, SKILL_ROOT)
    atomic_write_json(report, result)
    parsed = json.loads(report.read_text(encoding="utf-8"))
    assert parsed["ok"] is True
    with pytest.raises(FileExistsError):
        atomic_write_json(report, result)
