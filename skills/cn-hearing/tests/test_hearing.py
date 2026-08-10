from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "hearing.example.json"


def module():
    spec = importlib.util.spec_from_file_location("build_hearing_test", ROOT / "scripts" / "build_hearing.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sample():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_builds_matrix_and_refuses_overwrite(tmp_path: Path):
    tool = module()
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(sample(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "result"
    tool.build(input_path, output)
    assert {item.name for item in output.iterdir()} == {"hearing-workbook.json", "庭前庭审准备矩阵.md"}
    result = json.loads((output / "hearing-workbook.json").read_text(encoding="utf-8"))
    assert result["artifact_state"] == "lawyer_review_required"
    assert result["admission_state"] == "no_admissions_made"
    assert result["question_plan_state"] == "not_testimony_or_fact"
    assert any(item["gap_type"] == "issue_without_linked_evidence" for item in result["gaps"])
    with pytest.raises(FileExistsError):
        tool.build(input_path, output)


@pytest.mark.parametrize("action", ["transcribe", "summarize", "extract"])
def test_any_hearing_recording_content_action_is_blocked(action: str):
    tool = module()
    value = sample()
    value["recording_action"] = action
    assert any("庭审录音" in item for item in tool.validate(value, ROOT))


def test_hearing_audio_source_is_blocked_even_when_action_none():
    tool = module()
    value = sample()
    value["sources"].append({"source_id": "SRC-AUDIO", "kind": "hearing_audio", "file_name": "audio.bin", "mime_type": "application/octet-stream"})
    assert any("禁止处理庭审录音来源" in item for item in tool.validate(value, ROOT))


def test_disguised_hearing_audio_filename_is_blocked():
    tool = module()
    value = sample()
    value["sources"].append({"source_id": "SRC-AUDIO", "kind": "other", "file_name": "7月18日开庭备份.m4a", "mime_type": "audio/mp4"})
    assert any("SRC-AUDIO" in item for item in tool.validate(value, ROOT))


def test_dangling_issue_and_evidence_references_are_blocked():
    tool = module()
    value = sample()
    value["question_plans"][0]["issue_id"] = "ISSUE-MISSING"
    value["question_plans"][0]["evidence_ids"] = ["EVID-MISSING"]
    errors = tool.validate(value, ROOT)
    assert any("不存在争点" in item for item in errors)
    assert any("不存在证据" in item for item in errors)


def test_question_requires_nonempty_human_or_source_basis():
    tool = module()
    value = sample()
    value["question_plans"][0]["basis"]["confirmation_note"] = ""
    assert tool.validate(value, ROOT)


def test_external_submission_or_admission_is_blocked():
    tool = module()
    value = sample()
    value["external_action_requested"] = True
    assert any("事实承认" in item for item in tool.validate(value, ROOT))


def test_upstream_artifacts_must_belong_to_same_matter():
    tool = module()
    value = sample()
    value["evidence_map"]["matter_id"] = "MATTER-OTHER"
    assert any("cn-evidence-map" in item and "matter_id" in item for item in tool.validate(value, ROOT))
