from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


SKILL_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = SKILL_ROOT / "examples" / "evidence-map.example.json"


def load_module():
    path = SKILL_ROOT / "scripts" / "build_evidence_map.py"
    spec = importlib.util.spec_from_file_location("build_evidence_map_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_validates_and_builds_atomic_outputs(tmp_path: Path):
    module = load_module()
    value = example()
    validation = module.validate(value, SKILL_ROOT)
    assert validation["ok"], validation

    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "output"
    module.build(input_path, output)

    assert {path.name for path in output.iterdir()} == {
        "evidence-map.json",
        "evidence-matrix.csv",
        "证据映射报告.md",
        "validation.json",
    }
    result = json.loads((output / "evidence-map.json").read_text(encoding="utf-8"))
    assert result["artifact_state"] == "lawyer_review_required"
    assert result["coverage"]["facts_with_evidence"] == 2
    assert any(item["gap_type"] == "proof_purpose_unconfirmed" for item in result["gaps"])
    assert any(item["kind"] == "same_field_different_value" for item in result["potential_conflicts"])
    assert result["matrix"][0]["source_sha256"]
    assert result["matrix"][0]["three_nature"]["authenticity"] == "unreviewed"

    with pytest.raises(FileExistsError):
        module.build(input_path, output)


def test_proof_purpose_cannot_be_ai_inferred():
    module = load_module()
    value = example()
    value["evidence_fact_links"][0]["proof_purpose"]["basis_status"] = "ai_inferred"
    validation = module.validate(value, SKILL_ROOT)
    assert not validation["ok"]
    assert any("ai_inferred" in error for error in validation["errors"])


def test_human_confirmed_purpose_requires_confirmation_note():
    module = load_module()
    value = example()
    del value["evidence_fact_links"][0]["proof_purpose"]["confirmation_note"]
    validation = module.validate(value, SKILL_ROOT)
    assert not validation["ok"]
    assert any("证明目的" in error and "确认说明" in error for error in validation["errors"])


def test_three_nature_result_requires_matching_human_record():
    module = load_module()
    value = example()
    value["evidence"][0]["authenticity"] = "accepted"
    validation = module.validate(value, SKILL_ROOT)
    assert not validation["ok"]
    assert any("authenticity=accepted" in error for error in validation["errors"])

    confirmed = copy.deepcopy(value)
    confirmed["three_nature_reviews"].append(
        {
            "review_id": "REVIEW-AUTH-001",
            "evidence_id": "EVID-CONTRACT-001",
            "dimension": "authenticity",
            "status": "accepted",
            "reviewer_type": "human_user",
            "human_confirmation": True,
            "reviewed_at": "2026-07-18T10:00:00+08:00",
            "basis": "用户明确登记该审查状态，仍须执业律师复核",
            "source_spans": [],
        }
    )
    validation = module.validate(confirmed, SKILL_ROOT)
    assert validation["ok"], validation


def test_dangling_reference_is_rejected():
    module = load_module()
    value = example()
    value["fact_issue_links"][0]["issue_id"] = "ISSUE-NOT-FOUND"
    validation = module.validate(value, SKILL_ROOT)
    assert not validation["ok"]
    assert any("不存在的争点" in error for error in validation["errors"])


def test_source_location_requires_quote_and_locator():
    module = load_module()
    value = example()
    value["facts"][0]["source_spans"][0] = {
        "source_id": "SRC-CONTRACT-001",
        "quote": "",
    }
    validation = module.validate(value, SKILL_ROOT)
    assert not validation["ok"]
    assert any("缺少非空原文引文" in error for error in validation["errors"])
    assert any("缺少页码、段落或字符位置" in error for error in validation["errors"])


def test_hearing_recording_is_rejected_without_transcription():
    module = load_module()
    value = example()
    value["sources"].append(
        {
            "source_id": "SRC-HEARING-AUDIO",
            "file_name": "某次庭审录音.mp3",
            "sha256": "a" * 64,
            "mime_type": "audio/mpeg",
            "acquisition": "user_provided",
            "parse_status": "not_parsed",
        }
    )
    validation = module.validate(value, SKILL_ROOT)
    assert not validation["ok"]
    assert any("禁止处理庭审录音来源" in error for error in validation["errors"])
