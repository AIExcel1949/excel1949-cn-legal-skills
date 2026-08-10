from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "appeal.example.json"


def module():
    spec = importlib.util.spec_from_file_location("build_appeal_review_test", ROOT / "scripts" / "build_appeal_review.py")
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
    assert {item.name for item in output.iterdir()} == {"appeal-review.json", "上诉审查工作底稿.md"}
    result = json.loads((output / "appeal-review.json").read_text(encoding="utf-8"))
    assert result["artifact_state"] == "lawyer_review_required"
    with pytest.raises(FileExistsError):
        tool.build(input_path, output)


def test_appeal_request_is_preserved_verbatim_and_hashed():
    tool = module()
    value = sample()
    original = value["appeal_requests"][0]["verbatim_text"]
    result = tool.derive(value)
    assert result["request_integrity"][0]["verbatim_text"] == original
    assert len(result["request_integrity"][0]["text_sha256"]) == 64


def test_deadline_is_never_automatically_decided():
    tool = module()
    result = tool.derive(sample())
    assert result["deadline_audit"]["automatic_deadline_decision"] is None


def test_missing_source_reference_is_blocked():
    tool = module()
    value = sample()
    value["review_issues"][0]["supporting_citations"][0]["source_id"] = "SRC-MISSING"
    assert any("不存在来源" in item for item in tool.validate(value, ROOT))


def test_unverified_deadline_cannot_have_conclusion():
    tool = module()
    value = sample()
    value["deadline_review"]["lawyer_conclusion"] = "尚未逾期"
    assert any("未核验" in item for item in tool.validate(value, ROOT))


def test_claimed_new_evidence_requires_reason():
    tool = module()
    value = sample()
    value["new_evidence_explanations"][0]["not_submitted_reason"] = None
    assert any("未在原审提交原因" in item for item in tool.validate(value, ROOT))


def test_external_submission_is_blocked():
    tool = module()
    value = copy.deepcopy(sample())
    value["external_action_requested"] = True
    assert any("禁止自动签章" in item for item in tool.validate(value, ROOT))
