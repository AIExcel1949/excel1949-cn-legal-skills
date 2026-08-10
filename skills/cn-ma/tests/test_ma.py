from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "build_ma_matrix.py"
EXAMPLE = SKILL_DIR / "examples" / "ma-input.example.json"


def load_module():
    spec = importlib.util.spec_from_file_location("ma_builder", SCRIPT)
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


def test_fixed_review_and_no_execution(module, sample):
    result = module.build_matrix(sample)
    assert result["artifact_state"] == "lawyer_review_required"
    assert result["structure_selected_by_skill"] is False
    assert result["valuation_performed"] is False
    assert result["transaction_executed"] is False
    assert result["payment_performed"] is False
    assert result["structure_snapshot"] == sample["structure"]
    assert result["document_register"] == sample["document_sources"]


def test_unconfirmed_structure_blocks(module, sample):
    sample["structure"]["confirmation_status"] = "unconfirmed"
    result = module.build_matrix(sample)
    assert result["structure_gate"]["status"] == "blocked"
    assert any("不会自动选择结构" in item for item in result["global_blockers"])


def test_unconfirmed_valuation_blocks(module, sample):
    sample["structure"]["valuation_status"] = "under_review"
    result = module.build_matrix(sample)
    assert any("不会计算估值" in item for item in result["structure_gate"]["blockers"])


def test_undetermined_approval_blocks(module, sample):
    result = module.build_matrix(sample)
    approval = next(item for item in result["execution_matrix"] if item["item_id"] == "APPROVAL-AML-001")
    assert approval["matrix_status"] == "blocked"
    assert any("审批必要性" in item for item in approval["blockers"])


def test_missing_source_blocks(module, sample):
    sample["conditions_precedent"][0]["source_refs"] = ["DOC-MISSING"]
    result = module.build_matrix(sample)
    cp = next(item for item in result["execution_matrix"] if item["item_id"] == "CP-001")
    assert any("来源不存在" in item for item in cp["blockers"])


def test_missing_dependency_blocks(module, sample):
    sample["closing_deliverables"][0]["dependencies"] = ["NOT-FOUND"]
    result = module.build_matrix(sample)
    assert result["dependency_audit"]["status"] == "blocked"
    assert "CLOSE-001" in result["dependency_audit"]["missing_dependencies"]


def test_dependency_cycle_blocks(module, sample):
    sample["conditions_precedent"][0]["dependencies"] = ["CLOSE-001"]
    result = module.build_matrix(sample)
    assert result["dependency_audit"]["cycles"]
    assert any("环路" in item for item in result["global_blockers"])


def test_long_stop_is_not_calculated(module, sample):
    result = module.build_matrix(sample)
    assert result["long_stop_matrix"]["explicit_date"] == "2027-03-31"
    assert result["long_stop_matrix"]["date_calculated_by_skill"] is False


def test_missing_long_stop_date_blocks(module, sample):
    sample["long_stop"]["explicit_date"] = None
    result = module.build_matrix(sample)
    assert result["long_stop_matrix"]["status"] == "blocked"
    assert any("不会自行计算" in item for item in result["long_stop_matrix"]["blockers"])


def test_deterministic_output(module, sample):
    assert module.build_matrix(sample) == module.build_matrix(sample)


def test_atomic_output_refuses_overwrite(module, sample, tmp_path):
    destination = tmp_path / "result"
    module.write_atomic(module.build_matrix(sample), destination)
    assert (destination / "ma-matrix.json").exists()
    with pytest.raises(FileExistsError):
        module.write_atomic(module.build_matrix(sample), destination)


def test_markdown_has_guardrails(module, sample):
    markdown = module.render_markdown(module.build_matrix(sample))
    assert "Skill 选择结构：否" in markdown
    assert "不实施签署、交割、过户、付款" in markdown
