from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("retrieval_matrix", SKILL / "scripts" / "validate_retrieval_matrix.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


@pytest.fixture
def search_plan():
    task = json.loads((SKILL / "examples" / "research-task.example.json").read_text(encoding="utf-8"))
    base = {
        "source_classes": ["official_law", "official_case"],
        "legal_relationship_terms": ["买卖合同"], "element_terms": ["合同解除"],
        "fact_terms": ["部分履行"], "procedure_terms": [], "outcome_terms": ["返还", "损失赔偿"],
        "variant_terms": ["恢复原状"], "exclusion_terms": [], "execution_status": "not_run",
    }
    return {
        "schema_version": "1.0", "plan_id": "PLAN-001", "task": task,
        "branches": [
            {"branch_id": "BRANCH-support", "question_id": "Q-001", "purpose": "supportive", "query_strings": ["买卖合同 解除 返还 损失赔偿"], **base},
            {"branch_id": "BRANCH-adverse", "question_id": "Q-001", "purpose": "adverse", "query_strings": ["买卖合同 解除 不予支持 损失赔偿"], **base},
        ],
    }


@pytest.fixture
def case_comparison():
    dimensions = []
    for dimension in sorted(module.REQUIRED_DIMENSIONS):
        dimensions.append({
            "dimension": dimension, "comparison_status": "similar",
            "basis": "根据已打开的裁判原文与本案事实台账逐项比较。",
            "target_source_refs": ["FACT-001"], "case_locator": "裁判文书第5页本院认为第2段",
        })
    return {
        "schema_version": "1.0", "comparison_id": "COMPARE-001", "task_id": "RESEARCH-DEMO-001",
        "question_id": "Q-001", "case_record_id": "CASE-001", "verification_status": "verified",
        "source_url": "https://example.gov.cn/case/1", "dimensions": dimensions,
        "overall_status": "partially_analogous", "non_analogous_reasons": [],
        "limitations": ["个案裁判不等于一般规则。"],
    }


def test_search_plan_covers_supportive_and_adverse_branches(search_plan):
    result = module.validate_search_plan(search_plan)
    assert result["ok"] is True, result


def test_search_plan_requires_adverse_or_exception_branch(search_plan):
    search_plan["branches"].pop()
    result = module.validate_search_plan(search_plan)
    assert any("不利观点或例外" in item for item in result["errors"])


def test_search_plan_rejects_cross_branch_duplicate_query(search_plan):
    search_plan["branches"][1]["query_strings"] = list(search_plan["branches"][0]["query_strings"])
    result = module.validate_search_plan(search_plan)
    assert any("跨分支重复" in item for item in result["errors"])


def test_failed_search_branch_must_record_limitation(search_plan):
    search_plan["branches"][0]["execution_status"] = "failed"
    result = module.validate_search_plan(search_plan)
    assert any("限制" in item for item in result["errors"])


def test_case_comparison_requires_all_dimensions_and_locators(case_comparison):
    result = module.validate_case_comparison(case_comparison)
    assert result["ok"] is True, result
    value = copy.deepcopy(case_comparison)
    value["dimensions"].pop()
    assert module.validate_case_comparison(value)["ok"] is False
    value = copy.deepcopy(case_comparison)
    value["dimensions"][0]["case_locator"] = None
    assert any("缺少裁判原文定位" in item for item in module.validate_case_comparison(value)["errors"])


def test_unverified_case_cannot_receive_overall_analogy_status(case_comparison):
    case_comparison["verification_status"] = "pending"
    result = module.validate_case_comparison(case_comparison)
    assert any("未核验原文" in item for item in result["errors"])


def test_fixed_similarity_score_is_not_part_of_contract(case_comparison):
    case_comparison["similarity_score"] = 92
    result = module.validate_case_comparison(case_comparison)
    assert result["ok"] is False
    assert any("Additional properties" in item or "固定分数" in item for item in result["errors"])


def test_validation_is_deterministic(search_plan, case_comparison):
    assert module.validate_search_plan(search_plan) == module.validate_search_plan(copy.deepcopy(search_plan))
    assert module.validate_case_comparison(case_comparison) == module.validate_case_comparison(copy.deepcopy(case_comparison))
