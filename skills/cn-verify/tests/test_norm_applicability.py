from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
SPEC = importlib.util.spec_from_file_location("norm_applicability", SKILL / "scripts" / "validate_norm_applicability.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


@pytest.fixture
def verify_input():
    return json.loads((SKILL / "examples" / "verify-input.example.json").read_text(encoding="utf-8"))


@pytest.fixture
def assessment():
    confirmed = {"status": "confirmed", "reason": "已根据当前终检包与已核验原文逐项复核。"}
    return {
        "schema_version": "1.0", "assessment_id": "NORM-ASSESS-001", "matter_id": "MATTER-2026-DEMO",
        "as_of": "2026-07-18T09:00:00+08:00",
        "fact_period": {"start": "2025-01-01", "end": "2025-12-31", "status": "confirmed", "source_refs": ["FACT-loan-date"]},
        "norms": [{
            "norm_id": "NORM-001", "authority_id": "AUTH-CIVIL-CODE-LOAN", "article_locator": "相关条文，以法源台账引文为准",
            "origin": confirmed, "effect": confirmed, "temporal": confirmed, "geographic": confirmed,
            "subject": confirmed, "matter": confirmed, "procedure": confirmed,
            "applicability_status": "applicable", "reasons": ["在本工作底稿中作为待律师终审的候选依据。"],
        }],
        "conflicts": [],
    }


def codes(result):
    return {item["code"] for item in result["blockers"]}


def test_all_dimensions_confirmed_keeps_lawyer_gate(verify_input, assessment):
    result = module.validate_assessment(verify_input, assessment)
    assert result["ok"] is True, result
    assert result["state"] == "lawyer_review_required"


def test_uncertain_dimension_cannot_be_marked_applicable(verify_input, assessment):
    assessment["norms"][0]["temporal"] = {"status": "uncertain", "reason": "事实时点尚待复核。"}
    assert "NORM.INCONSISTENT_APPLICABILITY" in codes(module.validate_assessment(verify_input, assessment))


def test_repealed_or_unknown_authority_cannot_be_applicable(verify_input, assessment):
    verify_input["authorities"][0]["record"]["effect_status"] = "repealed"
    assert "NORM.INVALID_EFFECT" in codes(module.validate_assessment(verify_input, assessment))


def test_unresolved_conflict_blocks_delivery(verify_input, assessment):
    second = copy.deepcopy(assessment["norms"][0])
    second["norm_id"] = "NORM-002"
    assessment["norms"].append(second)
    assessment["conflicts"] = [{
        "conflict_id": "CONFLICT-001", "norm_ids": ["NORM-001", "NORM-002"],
        "conflict_type": "apparent", "resolution_status": "unresolved",
        "candidate_rule": "harmonized_interpretation", "reason": "两个规范的适用边界尚待区分。",
    }]
    assert "NORM.CONFLICT_UNRESOLVED" in codes(module.validate_assessment(verify_input, assessment))


def test_lawyer_confirmed_conflict_requires_review_metadata(verify_input, assessment):
    second = copy.deepcopy(assessment["norms"][0])
    second["norm_id"] = "NORM-002"
    assessment["norms"].append(second)
    assessment["conflicts"] = [{
        "conflict_id": "CONFLICT-002", "norm_ids": ["NORM-001", "NORM-002"],
        "conflict_type": "scope", "resolution_status": "lawyer_confirmed",
        "candidate_rule": "scope_distinction", "reason": "待记录律师确认。",
    }]
    result = module.validate_assessment(verify_input, assessment)
    assert result["state"] == "invalid"
    assert any("confirmed_by" in item or "confirmed_at" in item for item in result["errors"])


def test_unconfirmed_fact_period_blocks_temporal_conclusion(verify_input, assessment):
    assessment["fact_period"]["status"] = "unconfirmed"
    assert "NORM.FACT_PERIOD_UNCONFIRMED" in codes(module.validate_assessment(verify_input, assessment))


def test_unknown_authority_reference_is_invalid(verify_input, assessment):
    assessment["norms"][0]["authority_id"] = "AUTH-not-found"
    result = module.validate_assessment(verify_input, assessment)
    assert result["state"] == "invalid"
    assert any("不存在的法源" in item for item in result["errors"])


def test_assessment_is_deterministic(verify_input, assessment):
    assert module.validate_assessment(verify_input, assessment) == module.validate_assessment(copy.deepcopy(verify_input), copy.deepcopy(assessment))
