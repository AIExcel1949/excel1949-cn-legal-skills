from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def module():
    spec = importlib.util.spec_from_file_location("cn_complaint_build", ROOT / "scripts" / "build_complaint.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def example() -> dict:
    return json.loads((ROOT / "examples" / "complaint-input.example.json").read_text(encoding="utf-8"))


def test_example_validates_and_preserves_claim_exactly():
    mod = module()
    value = example()
    assert mod.validate_input(value)["ok"]
    result = mod.derive(value)
    assert result["complaint"]["claims"][0]["text_verbatim"] == value["draft_request"]["claims"][0]["text_verbatim"]
    assert result["claim_conservation_audit"]["all_exact"] is True
    assert result["artifact_state"] == "lawyer_review_required"


def test_missing_provenance_is_rejected():
    mod = module()
    value = example()
    claim = value["draft_request"]["claims"][0]
    claim.pop("user_confirmed")
    claim.pop("confirmation_note")
    result = mod.validate_input(value)
    assert not result["ok"]


def test_unresolved_conflict_blocks_but_does_not_mutate_claim():
    mod = module()
    value = example()
    value["declared_conflicts"] = [{"conflict_id": "CONFLICT-001", "description": "金额材料存在冲突", "status": "declared", "source_spans": [{"source_id": "SRC-CONTRACT-001", "locator": "第1页", "quote": "金额记载一"}]}]
    result = mod.derive(value)
    assert result["generation_status"] == "blocked"
    assert result["complaint"]["claims"][0]["text_verbatim"] == value["draft_request"]["claims"][0]["text_verbatim"]


def test_unverified_authority_blocks_generation():
    mod = module()
    value = example()
    value["research_report"]["records"][0]["verification_status"] = "pending"
    result = mod.derive(value)
    assert any(x["code"] == "authority_not_verified_current" for x in result["blockers"])


def test_missing_evidence_reference_is_rejected():
    mod = module()
    value = example()
    value["draft_request"]["evidence_ids"] = ["EVID-MISSING-001"]
    result = mod.validate_input(value)
    assert not result["ok"]
    assert any("不在 evidence_map.matrix" in x for x in result["errors"])


def test_atomic_build_refuses_overwrite_and_has_no_signature(tmp_path: Path):
    mod = module()
    source = tmp_path / "input.json"
    source.write_text(json.dumps(example(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "out"
    result = mod.build(source, output)
    assert result["generation_status"] == "draft_ready_for_lawyer_review"
    markdown = (output / "民事起诉状-待复核.md").read_text(encoding="utf-8")
    assert "不生成签名或印章" in markdown
    assert "起诉人签章" not in markdown
    with pytest.raises(FileExistsError):
        mod.build(source, output)


def test_calc_result_is_not_recomputed_and_unreviewed_reference_blocks():
    mod = module()
    value = copy.deepcopy(example())
    value["calculation_report"] = {"status": "calculated_unreviewed", "lawyer_reviewed": False, "calculations": [{"id": "total_001", "rounded_value": "9999.99"}]}
    value["draft_request"]["claims"][0]["calculation_id"] = "total_001"
    result = mod.derive(value)
    assert result["complaint"]["claims"][0]["text_verbatim"].endswith("10000元。")
    assert any(x["code"] == "calculation_unreviewed" for x in result["blockers"])
