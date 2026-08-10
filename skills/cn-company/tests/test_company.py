from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "build_company_matrix.py"
EXAMPLE = SKILL_DIR / "examples" / "company-input.example.json"


def load_module():
    spec = importlib.util.spec_from_file_location("company_builder", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module():
    return load_module()


@pytest.fixture
def sample():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_schemas_are_valid():
    for path in (SKILL_DIR / "schemas").glob("*.schema.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_example_validates(module, sample):
    module.validate(sample, module.INPUT_SCHEMA)


def test_fixed_review_state(module, sample):
    result = module.build_matrix(sample)
    assert result["artifact_state"] == "lawyer_review_required"
    assert result["resolution_validity_determined"] is False
    assert result["external_submission_performed"] is False
    assert result["shareholder_register"] == sample["shareholders"]
    assert result["governance_person_register"] == sample["governance_persons"]


def test_generates_seven_stages(module, sample):
    result = module.build_matrix(sample)
    assert len(result["task_matrix"]) == 7
    assert {item["stage"] for item in result["task_matrix"]} == {item[0] for item in module.STAGES}


def test_missing_current_charter_blocks(module, sample):
    sample["charter_versions"][0]["status"] = "unknown"
    result = module.build_matrix(sample)
    assert result["charter_gate"]["status"] == "blocked"
    assert any("现行章程" in item for item in result["global_blockers"])


def test_multiple_current_charters_block(module, sample):
    extra = dict(sample["charter_versions"][0])
    extra["charter_id"] = "CHARTER-OTHER"
    extra["source_id"] = "CHARTER-2025"
    sample["charter_versions"].append(extra)
    result = module.build_matrix(sample)
    assert result["charter_gate"]["status"] == "blocked"


def test_missing_charter_source_blocks(module, sample):
    sample["charter_versions"][0]["source_id"] = "MISSING-SOURCE"
    result = module.build_matrix(sample)
    assert any("章程来源不存在" in item for item in result["charter_gate"]["blockers"])


def test_missing_agenda_authority_blocks(module, sample):
    sample["agenda_items"][0]["authority_source_ids"] = []
    result = module.build_matrix(sample)
    assert result["agenda_authority_map"][0]["status"] == "blocked"


def test_undetermined_registration_blocks_only_review_stage(module, sample):
    result = module.build_matrix(sample)
    registration = [item for item in result["task_matrix"] if item["stage"] == "registration_disclosure"][0]
    assert registration["status"] == "blocked"
    assert any("登记必要性" in item for item in registration["blockers"])


def test_deterministic_output(module, sample):
    assert module.build_matrix(sample) == module.build_matrix(sample)


def test_atomic_output_refuses_overwrite(module, sample, tmp_path):
    destination = tmp_path / "result"
    module.write_atomic(module.build_matrix(sample), destination)
    assert (destination / "company-matrix.json").exists()
    with pytest.raises(FileExistsError):
        module.write_atomic(module.build_matrix(sample), destination)


def test_markdown_has_guardrails(module, sample):
    markdown = module.render_markdown(module.build_matrix(sample))
    assert "决议有效性：未判断" in markdown
    assert "不生成签名或印章" in markdown
