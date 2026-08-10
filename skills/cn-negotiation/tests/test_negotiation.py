from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from build_negotiation import (  # noqa: E402
    FORBIDDEN_EXTERNAL_KEYS,
    InputError,
    assert_no_internal_keys,
    build_external_preview,
    build_internal_workbook,
    encode_json,
    load_input,
    validate_semantics,
    write_pair_atomic,
)


EXAMPLE = SKILL_DIR / "examples" / "negotiation-input.example.json"
SCRIPT = SKILL_DIR / "scripts" / "build_negotiation.py"


def example():
    return load_input(EXAMPLE)


def _external_bytes_and_workbook():
    data, raw = example()
    external = build_external_preview(data)
    external_bytes = encode_json(external)
    return data, external, build_internal_workbook(data, raw, external_bytes)


def test_example_outputs_are_deterministic_and_schema_valid():
    data, raw = example()
    first_external = build_external_preview(data)
    second_external = build_external_preview(data)
    assert first_external == second_external
    external_bytes = encode_json(first_external)
    first_internal = build_internal_workbook(data, raw, external_bytes)
    second_internal = build_internal_workbook(data, raw, external_bytes)
    assert first_internal == second_internal
    for filename, value in (
        ("external-preview.schema.json", first_external),
        ("negotiation-workbook.schema.json", first_internal),
    ):
        schema = json.loads((SKILL_DIR / "schemas" / filename).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(value)


def test_states_and_action_controls_are_fixed():
    _, external, internal = _external_bytes_and_workbook()
    assert external["artifact_state"] == "lawyer_review_required"
    assert internal["artifact_state"] == "lawyer_review_required"
    assert internal["internal_only"] is True
    assert internal["external_use_permitted"] is False
    for controls in (external["action_controls"], internal["action_controls"]):
        assert set(controls.values()) == {False}


def test_internal_workbook_rejects_mismatched_external_bytes():
    data, raw = example()
    with pytest.raises(InputError, match="不一致"):
        build_internal_workbook(data, raw, b"{}\n")


def test_external_preview_contains_no_internal_fields_or_known_secret_amount():
    _, external, _ = _external_bytes_and_workbook()
    assert_no_internal_keys(external)
    serialized = json.dumps(external, ensure_ascii=False).casefold()
    for key in FORBIDDEN_EXTERNAL_KEYS:
        assert f'"{key.casefold()}"' not in serialized
    assert "780000" not in serialized
    assert "batna" not in serialized
    assert "底线" not in serialized


def test_literal_internal_phrase_in_external_workspace_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["external_workspace"]["issues"][0]["public_position"] = changed["internal_strategy"]["authorization"]["scope_notes"]
    with pytest.raises(InputError, match="授权备注"):
        validate_semantics(changed)


def test_internal_marker_in_external_workspace_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["external_workspace"]["issues"][0]["public_position"] = "我方授权上限见后续文本。"
    with pytest.raises(InputError, match="内部标记"):
        validate_semantics(changed)


def test_exact_authorization_amount_in_external_workspace_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["external_workspace"]["proposals"][0]["terms"][0]["offer_text"] = "拟以 780000 元作为本轮讨论数额。"
    with pytest.raises(InputError, match="授权金额"):
        validate_semantics(changed)


@pytest.mark.parametrize("offer_text", ["拟以 780,000.00 元讨论。", "拟以 78 万元讨论。"])
def test_formatted_authorization_amount_in_external_workspace_is_rejected(offer_text: str):
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["external_workspace"]["proposals"][0]["terms"][0]["offer_text"] = offer_text
    with pytest.raises(InputError, match="授权金额"):
        validate_semantics(changed)


def test_unconfirmed_client_authority_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["internal_strategy"]["authorization"]["confirmed_by_client"] = False
    with pytest.raises(InputError, match="授权未明示确认"):
        validate_semantics(changed)


def test_missing_confirmation_date_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["internal_strategy"]["authorization"]["confirmed_at"] = None
    with pytest.raises(InputError, match="缺少确认日期"):
        validate_semantics(changed)


def test_criteria_weights_must_sum_to_one_hundred():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["internal_strategy"]["evaluation_criteria"][0]["weight"] = 39
    with pytest.raises(InputError, match="权重合计"):
        validate_semantics(changed)


def test_assessments_must_match_all_proposals():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["internal_strategy"]["proposal_assessments"].pop()
    with pytest.raises(InputError, match="一一对应"):
        validate_semantics(changed)


def test_each_assessment_must_cover_every_criterion_once():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["internal_strategy"]["proposal_assessments"][0]["scores"].pop()
    with pytest.raises(InputError, match="各评分一次"):
        validate_semantics(changed)


def test_broken_issue_reference_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["external_workspace"]["proposals"][0]["terms"][0]["issue_id"] = "ISS-UNKNOWN"
    with pytest.raises(InputError, match="未定义编号"):
        validate_semantics(changed)


def test_duplicate_issue_id_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["external_workspace"]["issues"][1]["issue_id"] = changed["external_workspace"]["issues"][0]["issue_id"]
    with pytest.raises(InputError, match="issue_id 不得重复"):
        validate_semantics(changed)


def test_weighted_scores_are_computed_without_ranking():
    _, _, internal = _external_bytes_and_workbook()
    scores = {item["proposal_id"]: item["weighted_score"] for item in internal["proposal_comparison"]}
    assert scores == {"PRO-A": "77.20", "PRO-B": "80.60"}
    serialized = json.dumps(internal["proposal_comparison"], ensure_ascii=False)
    assert "不构成排名" in serialized
    assert '"rank"' not in serialized
    assert '"recommended"' not in serialized


def test_pending_confirmations_collect_proposals_minutes_and_next_steps():
    _, external, _ = _external_bytes_and_workbook()
    pairs = {(item["source_type"], item["source_id"]) for item in external["pending_confirmations"]}
    assert pairs == {
        ("proposal", "PRO-A"),
        ("proposal", "PRO-B"),
        ("meeting_item", "TMP-001"),
        ("next_step", "NEXT-001"),
        ("next_step", "NEXT-002"),
    }
    assert external["meeting_minutes"]["minutes_state"] == "record_only_not_commitment"


def test_conditional_exchange_preserves_both_sides_and_never_commits():
    _, external, _ = _external_bytes_and_workbook()
    exchange = external["proposals"][0]["conditional_exchanges"][0]
    assert exchange["give_text"]
    assert exchange["receive_text"]
    assert exchange["condition_text"]
    assert exchange["exchange_state"] == "proposed_conditional_exchange"
    assert "accepted" not in json.dumps(exchange)


def test_schema_rejects_accepted_term_status(tmp_path: Path):
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["external_workspace"]["proposals"][0]["terms"][0]["status"] = "accepted"
    path = tmp_path / "accepted.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(InputError, match="Schema 校验失败"):
        load_input(path)


def test_schema_rejects_deception_confirmation_false(tmp_path: Path):
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["internal_strategy"]["ethical_confirmation"]["no_deception"] = False
    path = tmp_path / "deception.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(InputError, match="Schema 校验失败"):
        load_input(path)


def test_duplicate_json_key_is_rejected(tmp_path: Path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
    with pytest.raises(InputError, match="重复 JSON 键"):
        load_input(path)


def test_atomic_output_refuses_existing_file_without_partial_creation(tmp_path: Path):
    internal_path = tmp_path / "internal.json"
    external_path = tmp_path / "external.json"
    external_path.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        write_pair_atomic(internal_path, b"internal", external_path, b"external")
    assert not internal_path.exists()
    assert external_path.read_text(encoding="utf-8") == "keep"


def test_atomic_output_refuses_same_path(tmp_path: Path):
    path = tmp_path / "same.json"
    with pytest.raises(InputError, match="路径不得相同"):
        write_pair_atomic(path, b"internal", path, b"external")


def test_cli_creates_two_new_files_and_then_refuses_overwrite(tmp_path: Path):
    internal_path = tmp_path / "internal.json"
    external_path = tmp_path / "external.json"
    command = [
        sys.executable,
        str(SCRIPT),
        str(EXAMPLE),
        "--internal-output",
        str(internal_path),
        "--external-output",
        str(external_path),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0
    assert internal_path.exists() and external_path.exists()
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode == 2
    assert "拒绝覆盖" in second.stderr


def test_cli_refuses_input_as_output_path(tmp_path: Path):
    external_path = tmp_path / "external.json"
    command = [
        sys.executable,
        str(SCRIPT),
        str(EXAMPLE),
        "--internal-output",
        str(EXAMPLE),
        "--external-output",
        str(external_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 2
    assert "输入与输出路径不得相同" in completed.stderr
    assert not external_path.exists()
