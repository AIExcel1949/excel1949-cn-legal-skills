from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from build_mediation import InputError, build_workbench, load_input, render_markdown, write_pair_atomic  # noqa: E402


EXAMPLE = SKILL_DIR / "examples" / "mediation-input.example.json"


def example():
    return load_input(EXAMPLE)


def test_example_is_deterministic_and_schema_valid():
    data, raw = example()
    first = build_workbench(data, raw)
    second = build_workbench(data, raw)
    assert first == second
    assert first["artifact_state"] == "lawyer_review_required"
    assert first["action_controls"] == {"auto_send": False, "auto_sign": False, "auto_submit": False, "external_use_permitted": False}
    schema = json.loads((SKILL_DIR / "schemas" / "mediation-output.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(first)


def test_amount_beyond_authority_is_blocked():
    data, _ = example()
    data = copy.deepcopy(data)
    data["proposals"][0]["amount"] = 200000
    data["proposals"][0]["payment_schedule"][0]["amount"] = 200000
    result = build_workbench(data, json.dumps(data, ensure_ascii=False, default=float).encode())
    assert not result["proposal_comparison"][0]["within_amount_authority"]
    assert any("超出" in item for item in result["blockers"])


def test_unauthorized_non_monetary_term_is_blocked():
    data, _ = example()
    data = copy.deepcopy(data)
    data["proposals"][0]["non_monetary_terms"].append({"term_key": "public_apology", "value": "yes", "description": "要求公开致歉"})
    result = build_workbench(data, json.dumps(data, ensure_ascii=False, default=float).encode())
    assert result["proposal_comparison"][0]["unauthorized_non_monetary_terms"] == ["public_apology"]


def test_external_preview_detects_internal_marker_and_note_copy():
    data, _ = example()
    data = copy.deepcopy(data)
    note = data["proposals"][0]["internal_notes"]
    data["proposals"][0]["public_offer_text"] = f"我方底线如下：{note}"
    result = build_workbench(data, json.dumps(data, ensure_ascii=False, default=float).encode())
    assert result["external_previews"][0]["preview_state"] == "blocked"
    assert any("内部标记" in item for item in result["blockers"])
    assert any("内部备注" in item for item in result["blockers"])


def test_missing_required_clause_is_reported():
    data, _ = example()
    data = copy.deepcopy(data)
    data["proposals"][1]["clauses"] = [item for item in data["proposals"][1]["clauses"] if item["category"] != "default"]
    result = build_workbench(data, json.dumps(data, ensure_ascii=False, default=float).encode())
    assert not result["proposal_comparison"][1]["clause_checklist"]["default"]
    assert any("条款清单缺失" in item for item in result["blockers"])


def test_unconfirmed_client_authority_is_global_blocker():
    data, _ = example()
    data = copy.deepcopy(data)
    data["authority"]["confirmed_by_client"] = False
    result = build_workbench(data, json.dumps(data, ensure_ascii=False, default=float).encode())
    assert any("未确认" in item for item in result["blockers"])


def test_atomic_pair_refuses_existing_without_touching_other(tmp_path: Path):
    json_path = tmp_path / "out.json"
    md_path = tmp_path / "out.md"
    json_path.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        write_pair_atomic(json_path, b"new", md_path, b"markdown")
    assert json_path.read_text(encoding="utf-8") == "keep"
    assert not md_path.exists()


def test_duplicate_json_key_is_rejected(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
    with pytest.raises(InputError, match="重复 JSON 键"):
        load_input(path)


def test_markdown_never_labels_output_sendable():
    data, raw = example()
    markdown = render_markdown(build_workbench(data, raw))
    assert "不得自动发送" in markdown
    assert "待执业律师复核" in markdown
