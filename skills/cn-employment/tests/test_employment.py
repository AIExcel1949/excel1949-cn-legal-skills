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

from build_employment_review import (  # noqa: E402
    AUTHOR,
    InputError,
    build_review,
    load_input,
    render_markdown,
    validate_semantics,
    write_pair_atomic,
)


EXAMPLE = SKILL_DIR / "examples" / "employment-input.example.json"
SCRIPT = SKILL_DIR / "scripts" / "build_employment_review.py"


def example():
    return load_input(EXAMPLE)


def test_example_is_deterministic_and_schema_valid():
    data, raw = example()
    first = build_review(data, raw)
    second = build_review(data, raw)
    assert first == second
    schema = json.loads((SKILL_DIR / "schemas" / "employment-output.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(first)
    assert first["author"] == AUTHOR
    assert first["artifact_state"] == "lawyer_review_required"
    assert set(first["action_controls"].values()) == {False}


def test_original_text_source_hash_and_status_are_preserved():
    data, raw = example()
    result = build_review(data, raw)
    assert result["sources"] == data["sources"]
    for source in result["sources"]:
        assert hashlib.sha256(source["original_text"].encode("utf-8")).hexdigest() == source["sha256"]
        assert source["verification_status"] in {"unverified", "source_checked", "lawyer_verified"}


def test_source_hash_mismatch_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["sources"][0]["original_text"] += "变更"
    with pytest.raises(InputError, match="SHA-256 不匹配"):
        validate_semantics(changed)


def test_verification_status_and_date_must_be_consistent():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["sources"][0]["verified_on"] = None
    with pytest.raises(InputError, match="必须填写核验日期"):
        validate_semantics(changed)


def test_relationship_candidates_are_counted_without_ranking_or_determination():
    data, raw = example()
    result = build_review(data, raw)
    matrix = {item["candidate_type"]: item for item in result["relationship_candidate_matrix"]}
    assert matrix["labor_relation"]["support_count"] == 2
    assert matrix["service_relation"]["support_count"] == 2
    assert all(item["status"] == "candidate_only_no_determination" for item in matrix.values())
    serialized = json.dumps(matrix, ensure_ascii=False)
    assert '"rank"' not in serialized and '"winner"' not in serialized


def test_unknown_source_reference_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["relationship_review"]["signals"][0]["source_ids"] = ["SRC-MISSING"]
    with pytest.raises(InputError, match="未定义编号"):
        validate_semantics(changed)


def test_unknown_authority_reference_is_rejected():
    data, _ = example()
    changed = copy.deepcopy(data)
    changed["lifecycle_reviews"][0]["authority_ids"] = ["EMP-NOT-REGISTERED"]
    with pytest.raises(InputError, match="法源引用未定义"):
        validate_semantics(changed)


def test_all_eight_lifecycle_categories_are_covered_in_example():
    data, raw = example()
    result = build_review(data, raw)
    assert result["coverage_gaps"] == []
    assert len({item["category"] for item in result["lifecycle_matrix"]}) == 8
    assert all(item["legal_characterization"] == "not_determined" for item in result["lifecycle_matrix"])


def test_missing_category_is_reported_as_gap_not_safe_default():
    data, raw = example()
    changed = copy.deepcopy(data)
    changed["lifecycle_reviews"] = [item for item in changed["lifecycle_reviews"] if item["category"] != "work_rules"]
    result = build_review(changed, json.dumps(changed, ensure_ascii=False).encode("utf-8"))
    assert result["coverage_gaps"] == ["work_rules"]
    assert any("work_rules" in item for item in result["blockers"])


def test_adverse_action_always_enters_human_decision_queue():
    data, raw = example()
    result = build_review(data, raw)
    queue = {item["action_id"]: item for item in result["human_decision_queue"]}
    assert "ACT-ROLE-CHANGE" in queue
    assert queue["ACT-ROLE-CHANGE"]["execution_permitted"] is False
    assert queue["ACT-ROLE-CHANGE"]["decision_state"] == "human_decision_required"
    assert "ACT-COLLECT" not in queue


def test_dispute_output_never_predicts_outcome():
    data, raw = example()
    dispute = build_review(data, raw)["dispute_review"]
    assert dispute["outcome_prediction"] == "not_performed"
    assert dispute["final_legal_conclusion"] == "lawyer_required"


def test_markdown_contains_author_hashes_and_execution_warning():
    data, raw = example()
    markdown = render_markdown(build_review(data, raw))
    assert AUTHOR in markdown
    assert data["sources"][0]["sha256"] in markdown
    assert "不得自动执行" in markdown
    assert "待执业律师判断" in markdown


def test_duplicate_json_key_is_rejected(tmp_path: Path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
    with pytest.raises(InputError, match="重复 JSON 键"):
        load_input(path)


def test_atomic_pair_refuses_overwrite_without_partial_output(tmp_path: Path):
    json_path = tmp_path / "review.json"
    md_path = tmp_path / "review.md"
    md_path.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        write_pair_atomic(json_path, b"{}", md_path, b"new")
    assert not json_path.exists()
    assert md_path.read_text(encoding="utf-8") == "keep"


def test_cli_writes_once_then_refuses_overwrite(tmp_path: Path):
    json_path = tmp_path / "review.json"
    md_path = tmp_path / "review.md"
    command = [sys.executable, str(SCRIPT), str(EXAMPLE), "--json-output", str(json_path), "--markdown-output", str(md_path)]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0
    assert second.returncode == 2
    assert "拒绝覆盖" in second.stderr
