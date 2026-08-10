from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def module():
    spec = importlib.util.spec_from_file_location("cn_legal_route", ROOT / "scripts" / "route.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sample() -> dict:
    return json.loads((ROOT / "examples" / "route.example.json").read_text(encoding="utf-8"))


def test_routes_confirmed_mixed_task():
    result = module().build(sample())
    assert result["routes"] == ["cn-dispute", "cn-transaction"]


def test_unknown_track_is_blocked():
    value = sample(); value["track"] = "unknown"; value.pop("mixed_tracks")
    assert "track_unknown" in module().build(value)["blockers"]


def test_unconfirmed_track_has_no_route():
    value = sample(); value["track_status"] = "unconfirmed"
    assert module().build(value)["routes"] == []


def test_urgent_flag_only_creates_human_escalation():
    result = module().build(sample())
    assert result["escalations"] == ["urgent_human_escalation:deadline"]


def test_refuses_overwrite(tmp_path: Path):
    output = tmp_path / "route.json"; output.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        module().write_new(output, module().build(sample()))


def test_requested_outputs_are_mapped_to_generators(tmp_path: Path):
    value = sample()
    value["track"] = "dispute"
    value.pop("mixed_tracks")
    value["requested_outputs"] = ["民事授权委托书（单位工作人员）", "财产保全申请书"]
    value["delivery_format"] = "docx"
    result = module().build(value, tmp_path)
    assert not result["blocked"]
    assert {
        item["template_id"] for item in result["requested_deliverables"]
    } == {"civil-organization-employee-power-attorney", "property-preservation-application"}
    assert all(item["skill"] == "cn-procedure" for item in result["requested_deliverables"])
    assert all(str(tmp_path) in item["output_dir"] for item in result["requested_deliverables"])
    assert result["runtime_profile"] == "codex_app"
    assert result["orchestration_mode"] == "codex_app_dynamic_experts"
    generator = next(step for step in result["execution_steps"] if step["kind"] == "generator")
    assert generator["executor"] == "dynamic_subagent"
    assert set(generator["authorized_template_ids"]) == {
        "civil-organization-employee-power-attorney",
        "property-preservation-application",
    }


def test_generic_authorization_requires_variant(tmp_path: Path):
    value = sample()
    value["track"] = "dispute"
    value.pop("mixed_tracks")
    value["requested_outputs"] = ["授权委托书"]
    value["delivery_format"] = "docx"
    result = module().build(value, tmp_path)
    assert result["blocked"]
    assert "deliverable_variant_required:authorization-document-selector" in result["blockers"]
    assert result["requested_deliverables"][0]["variant_options"] == [
        "民事授权委托书（律师）",
        "民事授权委托书（近亲属）",
        "民事授权委托书（单位工作人员）",
    ]


def test_unsupported_docx_is_blocked_instead_of_generic_conversion(tmp_path: Path):
    value = sample()
    value["track"] = "dispute"
    value.pop("mixed_tracks")
    value["requested_outputs"] = ["民事起诉状", "律师函", "一审代理词"]
    value["delivery_format"] = "docx"
    result = module().build(value, tmp_path)
    assert result["blocked"]
    assert {
        blocker for blocker in result["blockers"] if blocker.startswith("docx_not_supported:")
    } == {
        "docx_not_supported:civil-complaint",
        "docx_not_supported:lawyer-letter",
        "docx_not_supported:first-instance-agent-submission",
    }


def test_output_path_inside_skill_tree_is_rejected():
    route_module = module()
    with pytest.raises(route_module.RouteError):
        route_module.validate_output_path(ROOT / "runtime-route.json")
