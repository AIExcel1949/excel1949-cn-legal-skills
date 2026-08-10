from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from opinion_core import (  # noqa: E402
    InputError,
    atomic_write_workpaper,
    build_workpaper,
    gate_checks,
    load_json_file,
    schema_errors,
)


EXAMPLE = SKILL_DIR / "examples" / "training-opinion.example.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def clean_example() -> dict:
    data = load_example()
    data["facts"][1]["status"] = "confirmed"
    data["assumptions"][0]["status"] = "confirmed"
    return data


def test_example_is_valid_deterministic_and_blocked() -> None:
    data = load_example()
    fatal, blockers, warnings = gate_checks(data)
    assert fatal == []
    assert any("冲突事实" in item for item in blockers)
    assert any("关键假设" in item for item in blockers)
    assert any("教学测试模式" in item for item in warnings)
    first = build_workpaper(data)
    assert first == build_workpaper(copy.deepcopy(data))
    assert first["conclusions"][0]["status"] == "blocked"
    assert first["artifact_state"] == "lawyer_review_required"
    assert first["formal_opinion_issued"] is False
    assert schema_errors(first, output=True) == []


def test_clean_case_is_only_provisional_never_formal() -> None:
    output = build_workpaper(clean_example())
    assert output["blockers"] == []
    assert output["conclusions"][0]["status"] == "provisional_for_lawyer_review"
    assert output["formal_opinion_issued"] is False


def test_proposition_requires_both_fact_and_authority_trace() -> None:
    data = load_example()
    data["propositions"][0]["fact_ids"] = []
    fatal, _, _ = gate_checks(data)
    assert fatal
    data = load_example()
    data["propositions"][0]["authority_ids"] = []
    fatal, _, _ = gate_checks(data)
    assert fatal


def test_conclusion_requires_both_fact_and_authority_trace() -> None:
    data = load_example()
    data["conclusion_drafts"][0]["fact_ids"] = []
    fatal, _, _ = gate_checks(data)
    assert fatal
    data = load_example()
    data["conclusion_drafts"][0]["authority_ids"] = []
    fatal, _, _ = gate_checks(data)
    assert fatal


def test_unknown_trace_ids_are_fatal() -> None:
    data = load_example()
    data["propositions"][0]["fact_ids"] = ["fact-missing-999"]
    data["conclusion_drafts"][0]["authority_ids"] = ["authority-missing-999"]
    fatal, _, _ = gate_checks(data)
    assert any("未登记事实" in item for item in fatal)
    assert any("未登记法源" in item for item in fatal)


def test_stale_or_unverified_authority_blocks_conclusion() -> None:
    data = clean_example()
    data["authorities"][0]["effect_status"] = "expired"
    data["authorities"][0]["verification_status"] = "pending"
    output = build_workpaper(data)
    assert output["conclusions"][0]["status"] == "blocked"
    assert any("效力状态" in item for item in output["blockers"])
    assert any("官方全文核验" in item for item in output["blockers"])


def test_authority_verified_after_as_of_date_blocks() -> None:
    data = clean_example()
    data["authorities"][0]["verified_on"] = "2026-07-19"
    output = build_workpaper(data)
    assert any("晚于意见时点" in item for item in output["blockers"])
    assert output["conclusions"][0]["status"] == "blocked"


def test_unverified_fact_used_by_conclusion_blocks() -> None:
    data = clean_example()
    data["facts"][0]["status"] = "unverified"
    output = build_workpaper(data)
    assert output["conclusions"][0]["status"] == "blocked"
    assert any("unverified" in item for item in output["conclusions"][0]["blockers"])


def test_missing_adverse_proposition_warns_without_inventing_one() -> None:
    data = clean_example()
    data["propositions"] = [data["propositions"][0]]
    output = build_workpaper(data)
    assert any("缺少反对" in item for item in output["warnings"])
    assert len(output["propositions"]) == 1


def test_atomic_output_refuses_overwrite_and_is_not_formal(tmp_path: Path) -> None:
    output = tmp_path / "opinion"
    workpaper = build_workpaper(load_example())
    atomic_write_workpaper(workpaper, output)
    assert (output / "opinion-workpaper.json").is_file()
    markdown = (output / "opinion-workpaper.md").read_text(encoding="utf-8")
    assert "律师复核底稿" in markdown
    assert "不是正式法律意见书" in markdown
    with pytest.raises(InputError, match="拒绝覆盖"):
        atomic_write_workpaper(workpaper, output)


def test_symlink_input_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(source)
    with pytest.raises(InputError, match="符号链接"):
        load_json_file(link)
