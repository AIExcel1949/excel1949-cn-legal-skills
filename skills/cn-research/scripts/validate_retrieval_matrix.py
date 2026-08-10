#!/usr/bin/env python3
"""校验检索分支与类案比较矩阵，不调用或假装调用任何数据库。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_DIMENSIONS = {
    "legal_relationship", "dispute_issue", "decisive_facts", "evidence_structure",
    "procedure_stage", "applicable_rules", "result_relevance",
}
PLACEHOLDER_MARKERS = ("[", "]", "（待", "【待", "TODO", "TBD", "{{", "}}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入根节点必须是对象")
    return value


def validate_schema(value: dict[str, Any], name: str) -> list[str]:
    registry = Registry()
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if schema.get("$id"):
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    return [
        f"Schema {'.'.join(str(part) for part in error.absolute_path) or '<root>'}：{error.message}"
        for error in sorted(validator.iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
    ]


def validate_search_plan(value: dict[str, Any]) -> dict[str, Any]:
    errors = validate_schema(value, "search-plan.schema.json")
    warnings: list[str] = []
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    questions = {item["question_id"]: item for item in value["task"]["research_questions"]}
    branch_ids: set[str] = set()
    queries: dict[str, str] = {}
    purposes: dict[str, set[str]] = {question_id: set() for question_id in questions}
    for branch in value["branches"]:
        branch_id = branch["branch_id"]
        if branch_id in branch_ids:
            errors.append(f"检索分支编号重复：{branch_id}")
        branch_ids.add(branch_id)
        question_id = branch["question_id"]
        if question_id not in questions:
            errors.append(f"{branch_id} 引用不存在的研究问题：{question_id}")
            continue
        purposes[question_id].add(branch["purpose"])
        if branch["execution_status"] in {"partial", "failed"} and not branch.get("limitation"):
            errors.append(f"{branch_id} 未记录部分或失败执行的限制")
        if not any((branch[key] for key in ("legal_relationship_terms", "element_terms", "fact_terms", "procedure_terms", "outcome_terms"))):
            errors.append(f"{branch_id} 没有任何可回查的检索要素")
        for query in branch["query_strings"]:
            if any(marker in query for marker in PLACEHOLDER_MARKERS):
                errors.append(f"{branch_id} 检索式含未处理占位符：{query}")
            normalized = " ".join(query.split()).casefold()
            if normalized in queries and queries[normalized] != branch_id:
                errors.append(f"检索式跨分支重复：{queries[normalized]}、{branch_id}")
            queries[normalized] = branch_id
    for question_id, question in questions.items():
        if "supportive" not in purposes[question_id]:
            errors.append(f"{question_id} 缺少支持观点检索分支")
        if question.get("search_both_sides", True) and not purposes[question_id] & {"adverse", "exception"}:
            errors.append(f"{question_id} 缺少不利观点或例外规则检索分支")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def validate_case_comparison(value: dict[str, Any]) -> dict[str, Any]:
    errors = validate_schema(value, "case-comparison.schema.json")
    warnings: list[str] = []
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    dimensions = [item["dimension"] for item in value["dimensions"]]
    duplicates = sorted({item for item in dimensions if dimensions.count(item) > 1})
    if duplicates:
        errors.append(f"类案比较维度重复：{'、'.join(duplicates)}")
    missing = sorted(REQUIRED_DIMENSIONS - set(dimensions))
    if missing:
        errors.append(f"类案比较维度缺失：{'、'.join(missing)}")
    for item in value["dimensions"]:
        if value["verification_status"] == "verified" and item["comparison_status"] != "unknown" and not item["case_locator"]:
            errors.append(f"{item['dimension']} 缺少裁判原文定位")
    if value["verification_status"] != "verified" and value["overall_status"] != "not_assessed":
        errors.append("案例未核验原文时不得评估整体类比状态")
    if value["overall_status"] == "non_analogous" and not value["non_analogous_reasons"]:
        errors.append("判定不可类比时必须记录实质差异")
    if any(key in value for key in ("score", "similarity_score", "probability", "win_rate")):
        errors.append("不得用固定分数或胜率代替逐维度比较")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description="校验检索分支或类案比较矩阵")
    parser.add_argument("kind", choices=("search-plan", "case-comparison"))
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    value = load_json(args.input)
    result = validate_search_plan(value) if args.kind == "search-plan" else validate_case_comparison(value)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
