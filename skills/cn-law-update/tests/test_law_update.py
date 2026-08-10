from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from update_core import (  # noqa: E402
    InputError,
    atomic_write_report,
    build_report,
    determine_gate,
    gate_checks,
    load_json_file,
    report_schema_errors,
    text_sha256,
)


EXAMPLE = SKILL_DIR / "examples" / "training-update.example.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_training_example_is_valid_and_deterministic() -> None:
    data = load_example()
    fatal, blockers, warnings = gate_checks(data)
    assert fatal == []
    assert blockers == []
    assert warnings == []

    first = build_report(data)
    second = build_report(copy.deepcopy(data))
    assert first == second
    assert first["gate"]["status"] == "training_only"
    assert first["summary"] == {
        "change_count": 2,
        "added": 1,
        "removed": 0,
        "modified": 1,
        "unchanged": 1,
        "affected_artifact_count": 3,
    }
    assert first["impacted_skills"] == ["cn-deadline", "cn-deadline-demo", "cn-procedure"]
    assert first["impacted_templates"] == ["template-application-demo"]
    assert first["impacted_prior_conclusions"] == ["conclusion-deadline-demo"]
    assert first["gate"]["production_files_modified"] is False
    assert report_schema_errors(first) == []


def test_hash_mismatch_becomes_gate_blocker() -> None:
    data = load_example()
    data["new_version"]["units"][0]["text"] += "变更"
    fatal, blockers, _ = gate_checks(data)
    assert fatal == []
    assert any("SHA-256" in item for item in blockers)


def test_page_title_cannot_be_original_text() -> None:
    data = load_example()
    data["new_version"]["units"] = [
        {"unit_id": "title-only", "locator": "网页标题", "text": "仅有网页标题"}
    ]
    data["new_version"]["source"]["page_title"] = "仅有网页标题"
    data["new_version"]["text_sha256"] = text_sha256(data["new_version"])
    fatal, blockers, _ = gate_checks(data)
    assert fatal == []
    assert any("网页标题" in item for item in blockers)


def test_output_is_atomic_and_refuses_overwrite(tmp_path: Path) -> None:
    report = build_report(load_example())
    output = tmp_path / "report"
    atomic_write_report(report, output)
    assert (output / "change-report.json").is_file()
    assert (output / "change-report.md").is_file()
    with pytest.raises(InputError, match="拒绝覆盖"):
        atomic_write_report(report, output)


def test_input_symlink_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(source)
    with pytest.raises(InputError, match="符号链接"):
        load_json_file(link)


def test_production_training_source_is_blocked() -> None:
    data = load_example()
    data["mode"] = "production"
    fatal, blockers, _ = gate_checks(data)
    assert fatal == []
    assert any("教学测试来源" in item for item in blockers)


def test_manual_approval_never_authorizes_automatic_update() -> None:
    data = load_example()
    data["mode"] = "production"
    data["impact_claims"][0]["review_status"] = "confirmed"
    data["review_record"] = {
        "reviewer": "张某某",
        "reviewer_role": "执业律师",
        "reviewed_at": "2026-07-18T11:00:00+08:00",
        "decision": "approved_manual_update",
        "checklist": {
            "official_text_compared": True,
            "effect_status_verified": True,
            "transitional_rules_checked": True,
            "all_impacts_reviewed": True,
            "manual_update_plan_approved": True,
        },
    }
    changes = [{"unit_id": "article-1"}]
    status, reasons = determine_gate(data, [], changes)
    assert status == "approved_for_manual_update"
    assert any("未修改生产文件" in item for item in reasons)
