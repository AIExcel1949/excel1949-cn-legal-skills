from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from diligence_core import (  # noqa: E402
    InputError,
    atomic_write_workpaper,
    build_workpaper,
    gate_checks,
    load_json_file,
    schema_errors,
)


EXAMPLE = SKILL_DIR / "examples" / "training-diligence.example.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_is_valid_deterministic_and_partitioned() -> None:
    data = load_example()
    fatal, blockers, warnings = gate_checks(data)
    assert fatal == []
    assert blockers == []
    assert any("教学测试模式" in item for item in warnings)
    first = build_workpaper(data)
    second = build_workpaper(copy.deepcopy(data))
    assert first == second
    assert first["artifact_state"] == "lawyer_review_required"
    assert first["transaction_assessment"] == "not_performed"
    assert [item["finding_id"] for item in first["legal_findings"]] == ["finding-demo-002"]
    assert schema_errors(first, output=True) == []


def test_not_provided_is_not_rewritten_as_nonexistent() -> None:
    output = build_workpaper(load_example())
    missing = output["not_provided_materials"][0]
    assert missing["status"] == "partial"
    assert "不推定" in missing["interpretation_limit"]
    assert "不存在" in missing["interpretation_limit"]


def test_every_finding_requires_a_source_span() -> None:
    data = load_example()
    data["findings"][0]["source_spans"] = []
    fatal, _, _ = gate_checks(data)
    assert any("minItems" in item or "non-empty" in item or "should be non-empty" in item or "[]" in item for item in fatal)


def test_unknown_span_reference_is_fatal() -> None:
    data = load_example()
    data["findings"][0]["source_spans"][0]["span_id"] = "span-missing-999"
    fatal, _, _ = gate_checks(data)
    assert any("未登记来源定位" in item for item in fatal)


def test_legal_finding_requires_authority_and_official_verification() -> None:
    data = load_example()
    data["findings"][1]["authority_ids"] = []
    fatal, _, _ = gate_checks(data)
    assert fatal
    data = load_example()
    data["authorities"][0]["verification_status"] = "pending"
    fatal, blockers, _ = gate_checks(data)
    assert fatal == []
    assert any("官方全文核验" in item for item in blockers)


def test_unverified_hash_and_post_cutoff_document_are_blockers() -> None:
    data = load_example()
    data["documents"][0]["hash_verified"] = False
    data["documents"][0]["received_at"] = "2026-07-19T10:00:00+08:00"
    fatal, blockers, _ = gate_checks(data)
    assert fatal == []
    assert any("SHA-256" in item for item in blockers)
    assert any("晚于" in item for item in blockers)


def test_management_representation_stays_separate_and_warns() -> None:
    output = build_workpaper(load_example())
    assert len(output["management_representations"]) == 1
    assert any("尚未经独立资料" in item for item in output["warnings"])
    assert all(item["finding_id"] != "representation-demo-001" for item in output["fact_findings"])


def test_atomic_output_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "workpaper"
    workpaper = build_workpaper(load_example())
    atomic_write_workpaper(workpaper, output)
    assert (output / "diligence-workpaper.json").is_file()
    assert (output / "diligence-workpaper.md").is_file()
    with pytest.raises(InputError, match="拒绝覆盖"):
        atomic_write_workpaper(workpaper, output)


def test_symlink_input_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(source)
    with pytest.raises(InputError, match="符号链接"):
        load_json_file(link)
