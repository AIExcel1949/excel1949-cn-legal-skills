from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from build_privacy_review import (  # noqa: E402
    AUTHOR,
    InputError,
    build_review,
    load_input,
    render_markdown,
    validate_semantics,
    write_pair_atomic,
)


EXAMPLE = SKILL_DIR / "examples" / "privacy-input.example.json"
SCRIPT = SKILL_DIR / "scripts" / "build_privacy_review.py"


def example():
    return load_input(EXAMPLE)


def test_example_is_deterministic_and_schema_valid():
    data, raw = example()
    first = build_review(data, raw)
    second = build_review(data, raw)
    assert first == second
    schema = json.loads((SKILL_DIR / "schemas" / "privacy-output.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(first)
    assert first["author"] == AUTHOR
    assert first["artifact_state"] == "lawyer_review_required"
    assert set(first["action_controls"].values()) == {False}


def test_original_text_source_hash_and_verification_state_are_preserved():
    data, raw = example()
    result = build_review(data, raw)
    assert result["sources"] == data["sources"]
    for source in result["sources"]:
        assert hashlib.sha256(source["original_text"].encode("utf-8")).hexdigest() == source["sha256"]
        assert "verification_status" in source and "verified_on" in source


def test_source_hash_mismatch_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["sources"][0]["original_text"] += "改写"
    with pytest.raises(InputError, match="SHA-256 不匹配"):
        validate_semantics(changed)


def test_verified_source_requires_verification_date():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["sources"][0]["verified_on"] = None
    with pytest.raises(InputError, match="必须填写核验日期"):
        validate_semantics(changed)


def test_unknown_official_authority_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["authority_ids"] = ["PRV-NOT-REGISTERED"]
    with pytest.raises(InputError, match="法源引用未定义"):
        validate_semantics(changed)


def test_broken_data_item_reference_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["processing_activities"][0]["data_item_ids"] = ["DAT-MISSING"]
    with pytest.raises(InputError, match="未定义编号"):
        validate_semantics(changed)


def test_cross_border_false_requires_not_applicable_only():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["processing_activities"][0]["cross_border"]["mechanism_candidates"] = ["unknown"]
    with pytest.raises(InputError, match="必须仅为 not_applicable"):
        validate_semantics(changed)


def test_cross_border_true_cannot_use_not_applicable():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["processing_activities"][1]["cross_border"]["mechanism_candidates"] = ["not_applicable"]
    with pytest.raises(InputError, match="不得使用 not_applicable"):
        validate_semantics(changed)


def test_example_pia_covers_sensitive_minor_recipient_and_cross_border_activities():
    data, raw = example()
    result = build_review(data, raw)
    assert result["pia_gaps"] == []
    assert result["pia_matrix"][0]["automatic_approval"] is False
    assert result["pia_matrix"][0]["assessment_state"] == "lawyer_review_required"


def test_missing_pia_coverage_is_reported_not_approved():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["pia_records"][0]["activity_ids"] = ["ACT-ACCOUNT"]
    result = build_review(changed, json.dumps(changed, ensure_ascii=False).encode("utf-8"))
    assert result["pia_gaps"] == ["ACT-LOG-SUPPORT"]
    assert any("ACT-LOG-SUPPORT" in blocker for blocker in result["blockers"])


def test_inventory_classification_stays_candidate_and_deletion_is_disabled():
    data, raw = example()
    result = build_review(data, raw)
    assert all(item["classification_state"] == "candidate_only_no_determination" for item in result["inventory_matrix"])
    assert all(item["automatic_deletion_permitted"] is False for item in result["inventory_matrix"])


def test_legal_basis_recipient_and_cross_border_remain_candidates():
    data, raw = example()
    result = build_review(data, raw)
    for activity in result["processing_matrix"]:
        assert activity["legal_basis_state"] == "candidate_only_no_selection"
        assert activity["recipient_relationship_state"] == "candidate_only_no_determination"
        assert activity["cross_border_mechanism_state"] == "candidate_only_no_selection"
        assert activity["legality_conclusion"] == "not_determined"


def test_incident_notification_tasks_never_permit_notification():
    data, raw = example()
    queue = build_review(data, raw)["incident_task_queue"]
    assert queue
    assert all(item["execution_permitted"] is False for item in queue)
    assert all(item["notification_permitted"] is False for item in queue)
    assert {item["severity_candidate"] for item in queue} == {"unknown"}
    assert any(item["action_type"] == "assess_notification" for item in queue)


def test_delete_request_never_executes_automatically():
    data, raw = example()
    request = build_review(data, raw)["individual_request_queue"][0]
    assert request["request_type"] == "delete"
    assert request["auto_execute"] is False
    assert request["execution_permitted"] is False
    assert request["lawyer_review_required"] is True


def test_markdown_contains_author_hash_and_safety_warnings():
    data, raw = example()
    markdown = render_markdown(build_review(data, raw))
    assert AUTHOR in markdown
    assert data["sources"][0]["sha256"] in markdown
    assert "不得自动删除" in markdown
    assert "不得自动通知" in markdown
    assert "未作认定" in markdown


def test_duplicate_json_key_is_rejected(tmp_path: Path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
    with pytest.raises(InputError, match="重复 JSON 键"):
        load_input(path)


def test_atomic_pair_refuses_overwrite_without_partial_output(tmp_path: Path):
    json_path = tmp_path / "review.json"
    md_path = tmp_path / "review.md"
    json_path.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        write_pair_atomic(json_path, b"new", md_path, b"markdown")
    assert json_path.read_text(encoding="utf-8") == "keep"
    assert not md_path.exists()


def test_cli_writes_once_then_refuses_overwrite(tmp_path: Path):
    json_path = tmp_path / "review.json"
    md_path = tmp_path / "review.md"
    command = [sys.executable, str(SCRIPT), str(EXAMPLE), "--json-output", str(json_path), "--markdown-output", str(md_path)]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0
    assert second.returncode == 2
    assert "拒绝覆盖" in second.stderr
