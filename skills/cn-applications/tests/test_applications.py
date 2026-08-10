from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "application.example.json"


def module():
    spec = importlib.util.spec_from_file_location("build_application_test", ROOT / "scripts" / "build_application.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sample():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_builds_json_markdown_and_refuses_overwrite(tmp_path: Path):
    tool = module()
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(sample(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "result"
    tool.build(input_path, output)
    assert {item.name for item in output.iterdir()} == {"application-workpaper.json", "程序申请工作底稿.md"}
    result = json.loads((output / "application-workpaper.json").read_text(encoding="utf-8"))
    assert result["artifact_state"] == "lawyer_review_required"
    assert result["material_gaps"][0]["material_id"] == "MAT-002"
    with pytest.raises(FileExistsError):
        tool.build(input_path, output)


def test_request_requires_source_or_user_confirmation():
    tool = module()
    value = sample()
    value["requested_relief"][0]["basis"] = {"basis_type": "user_confirmed", "confirmed_at": "2026-07-18T09:00:00+08:00", "confirmation_note": ""}
    assert tool.validate(value, ROOT)


def test_unverified_deadline_cannot_contain_conclusion():
    tool = module()
    value = sample()
    value["deadline_review"]["conclusion"] = "尚有三日"
    assert any("deadline_review" in item for item in tool.validate(value, ROOT))


def test_verified_security_requires_registered_authority():
    tool = module()
    value = sample()
    value["security_review"] = {"status": "verified", "conclusion": "待按受理机构要求复核", "authority_ids": ["AUTH-MISSING"]}
    errors = tool.validate(value, ROOT)
    assert any("不存在法源" in item for item in errors)


def test_external_signature_or_submission_request_is_blocked():
    tool = module()
    value = sample()
    value["external_action_requested"] = True
    assert any("禁止自动签名" in item for item in tool.validate(value, ROOT))


def test_all_routes_remain_lawyer_review_required():
    tool = module()
    for route in tool.ROUTES:
        value = copy.deepcopy(sample())
        value["application_type"] = route
        result = tool.derive(value)
        assert result["artifact_state"] == "lawyer_review_required"
        assert all(item["status"] == "lawyer_review_required" for item in result["routing_checklist"])


def test_source_span_must_reference_registered_source():
    tool = module()
    value = sample()
    value["supporting_facts"][0]["basis"]["source_id"] = "SRC-MISSING"
    assert any("引用不存在来源" in item for item in tool.validate(value, ROOT))
