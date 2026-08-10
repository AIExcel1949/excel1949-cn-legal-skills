#!/usr/bin/env python3
"""Build a deterministic M&A execution matrix without executing a transaction."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = SKILL_DIR / "schemas" / "ma-input.schema.json"
OUTPUT_SCHEMA = SKILL_DIR / "schemas" / "ma-output.schema.json"
CATEGORIES = (
    ("approvals", "审批"),
    ("conditions_precedent", "先决条件"),
    ("representations_warranties", "陈述与保证"),
    ("covenants", "承诺"),
    ("indemnities", "赔偿"),
    ("closing_deliverables", "交割交付物"),
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(instance: Any, schema_path: Path) -> None:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance),
        key=lambda err: list(err.absolute_path),
    )
    if errors:
        detail = "; ".join(f"{'/'.join(map(str, err.absolute_path)) or '<root>'}: {err.message}" for err in errors)
        raise ValueError(f"Schema validation failed: {detail}")


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    cycles: set[tuple[str, ...]] = set()
    visiting: list[str] = []
    visited: set[str] = set()

    def normalize(cycle: list[str]) -> tuple[str, ...]:
        body = cycle[:-1]
        rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
        best = min(rotations)
        return best + (best[0],)

    def walk(node: str) -> None:
        if node in visiting:
            start = visiting.index(node)
            cycles.add(normalize(visiting[start:] + [node]))
            return
        if node in visited:
            return
        visiting.append(node)
        for dependency in graph.get(node, []):
            if dependency in graph:
                walk(dependency)
        visiting.pop()
        visited.add(node)

    for node in sorted(graph):
        walk(node)
    return [list(cycle) for cycle in sorted(cycles)]


def build_matrix(data: dict[str, Any]) -> dict[str, Any]:
    authority_ids = {item["source_id"] for item in data["authority_sources"]}
    document_ids = {item["source_id"] for item in data["document_sources"]}
    source_ids = authority_ids | document_ids
    global_blockers: list[str] = []
    warnings: list[str] = []

    structure_blockers: list[str] = []
    structure = data["structure"]
    if structure["confirmation_status"] != "user_confirmed":
        structure_blockers.append("交易结构未经用户确认；Skill 不会自动选择结构。")
    if structure["transaction_form"] == "undetermined":
        structure_blockers.append("交易形式尚未确定。")
    if not structure["structure_label"].strip():
        structure_blockers.append("交易结构描述为空。")
    if not structure["source_refs"]:
        structure_blockers.append("交易结构未绑定来源文件。")
    missing_structure_sources = sorted(set(structure["source_refs"]) - source_ids)
    if missing_structure_sources:
        structure_blockers.append(f"交易结构来源不存在：{', '.join(missing_structure_sources)}。")
    if structure["valuation_status"] != "user_confirmed":
        structure_blockers.append("估值未由用户确认；Skill 不会计算估值。")
    global_blockers.extend(structure_blockers)

    authority_register = []
    for source in data["authority_sources"]:
        source_blockers = []
        if source["effect_status"] != "effective":
            source_blockers.append("法源效力未确认为现行有效。")
        authority_register.append({**source, "status": "blocked" if source_blockers else "registered_for_lawyer_review", "blockers": source_blockers})
        global_blockers.extend(f"法源 {source['source_id']}：{item}" for item in source_blockers)

    raw_items: list[tuple[str, str, dict[str, Any]]] = []
    for category, label in CATEGORIES:
        raw_items.extend((category, label, item) for item in data[category])
    raw_items.append(("long_stop", "长停日期规则", data["long_stop"]))

    item_ids = [item["item_id"] for _, _, item in raw_items]
    duplicated_ids = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
    if duplicated_ids:
        global_blockers.append(f"执行事项 ID 重复：{', '.join(duplicated_ids)}。")
    known_ids = set(item_ids)
    graph = {item["item_id"]: list(item["dependencies"]) for _, _, item in raw_items}
    missing_dependencies: dict[str, list[str]] = {
        item_id: sorted(set(dependencies) - known_ids)
        for item_id, dependencies in graph.items()
        if set(dependencies) - known_ids
    }
    self_dependencies = sorted(item_id for item_id, dependencies in graph.items() if item_id in dependencies)
    cycles = find_cycles(graph)
    for item_id, missing in missing_dependencies.items():
        global_blockers.append(f"事项 {item_id} 的依赖不存在：{', '.join(missing)}。")
    if self_dependencies:
        global_blockers.append(f"存在自依赖事项：{', '.join(self_dependencies)}。")
    for cycle in cycles:
        global_blockers.append(f"依赖形成环路：{' -> '.join(cycle)}。")

    execution_matrix: list[dict[str, Any]] = []
    for category, label, item in raw_items:
        if category == "long_stop":
            continue
        blockers: list[str] = []
        missing_sources = sorted(set(item["source_refs"]) - source_ids)
        if not item["source_refs"]:
            blockers.append("事项未绑定来源。")
        if missing_sources:
            blockers.append(f"来源不存在：{', '.join(missing_sources)}。")
        if not item["responsible_party"].strip():
            blockers.append("未指定责任人。")
        if item["item_id"] in missing_dependencies:
            blockers.append(f"依赖不存在：{', '.join(missing_dependencies[item['item_id']])}。")
        if item["item_id"] in self_dependencies or any(item["item_id"] in cycle for cycle in cycles):
            blockers.append("依赖关系存在自依赖或环路。")
        if category == "approvals":
            if item["determination"] == "to_be_determined":
                blockers.append("审批必要性待律师判断。")
            if item["status"] == "obtained" and not item["completion_evidence"].strip():
                blockers.append("审批标记为已取得但未登记完成证据。")
        else:
            if item["status"] == "to_be_determined":
                blockers.append("事项状态待确认。")
            if item["status"] in {"satisfied", "waived"} and not item["completion_evidence"].strip():
                blockers.append("事项状态需要完成或豁免证据。")
        execution_matrix.append(
            {
                "item_id": item["item_id"],
                "category": category,
                "category_label": label,
                "description": item["description"],
                "responsible_party": item["responsible_party"],
                "benefiting_party": item.get("benefiting_party", ""),
                "input_status": item["status"],
                "determination": item.get("determination"),
                "source_refs": sorted(item["source_refs"]),
                "dependencies": sorted(item["dependencies"]),
                "completion_evidence": item["completion_evidence"],
                "matrix_status": "blocked" if blockers else "pending_lawyer_review",
                "blockers": sorted(set(blockers)),
            }
        )
        global_blockers.extend(f"事项 {item['item_id']}：{blocker}" for blocker in blockers)

    long_stop = data["long_stop"]
    long_stop_blockers: list[str] = []
    if long_stop["rule_status"] != "user_confirmed":
        long_stop_blockers.append("长停日期规则未由用户确认。")
    if not long_stop["rule_text"].strip():
        long_stop_blockers.append("长停日期规则文本为空。")
    if long_stop["explicit_date"] is None:
        long_stop_blockers.append("未输入显式长停日期；脚本不会自行计算。")
    if not long_stop["responsible_party"].strip():
        long_stop_blockers.append("未指定长停日期监控责任人。")
    missing_long_stop_sources = sorted(set(long_stop["source_refs"]) - source_ids)
    if not long_stop["source_refs"]:
        long_stop_blockers.append("长停日期规则未绑定来源。")
    if missing_long_stop_sources:
        long_stop_blockers.append(f"长停日期来源不存在：{', '.join(missing_long_stop_sources)}。")
    if long_stop["item_id"] in missing_dependencies:
        long_stop_blockers.append(f"依赖不存在：{', '.join(missing_dependencies[long_stop['item_id']])}。")
    if long_stop["item_id"] in self_dependencies or any(long_stop["item_id"] in cycle for cycle in cycles):
        long_stop_blockers.append("依赖关系存在自依赖或环路。")
    global_blockers.extend(f"长停日期：{item}" for item in long_stop_blockers)

    if not data["authority_sources"]:
        warnings.append("未登记任何官方法源；监管与公司法路径须另行核验。")
    if not data["approvals"]:
        warnings.append("审批清单为空，不表示交易无需审批。")

    result = {
        "schema_version": "1.0",
        "matter_id": data["matter_id"],
        "as_of_date": data["as_of_date"],
        "input_sha256": hashlib.sha256(canonical_bytes(data)).hexdigest(),
        "structure_snapshot": structure,
        "structure_gate": {
            "confirmation_status": structure["confirmation_status"],
            "structure_label": structure["structure_label"],
            "transaction_form": structure["transaction_form"],
            "valuation_status": structure["valuation_status"],
            "status": "blocked" if structure_blockers else "pending_lawyer_review",
            "blockers": structure_blockers,
        },
        "authority_register": authority_register,
        "document_register": data["document_sources"],
        "execution_matrix": execution_matrix,
        "dependency_audit": {
            "known_item_ids": sorted(known_ids),
            "duplicate_item_ids": duplicated_ids,
            "missing_dependencies": missing_dependencies,
            "self_dependencies": self_dependencies,
            "cycles": cycles,
            "status": "blocked" if duplicated_ids or missing_dependencies or self_dependencies or cycles else "passed_structural_check",
        },
        "long_stop_matrix": {
            "item_id": long_stop["item_id"],
            "rule_status": long_stop["rule_status"],
            "rule_text": long_stop["rule_text"],
            "explicit_date": long_stop["explicit_date"],
            "responsible_party": long_stop["responsible_party"],
            "source_refs": sorted(long_stop["source_refs"]),
            "dependencies": sorted(long_stop["dependencies"]),
            "date_calculated_by_skill": False,
            "status": "blocked" if long_stop_blockers else "pending_lawyer_review",
            "blockers": sorted(set(long_stop_blockers)),
        },
        "global_blockers": sorted(set(global_blockers)),
        "warnings": sorted(set(warnings)),
        "structure_selected_by_skill": False,
        "valuation_performed": False,
        "transaction_executed": False,
        "payment_performed": False,
        "artifact_state": "lawyer_review_required",
    }
    validate(result, OUTPUT_SCHEMA)
    return result


def render_markdown(result: dict[str, Any]) -> str:
    rows = [
        f"| {item['item_id']} | {item['category_label']} | {item['responsible_party'] or '未指定'} | "
        f"{item['matrix_status']} | {'；'.join(item['blockers']) or '无结构化阻断项'} |"
        for item in result["execution_matrix"]
    ]
    blockers = "\n".join(f"- {item}" for item in result["global_blockers"]) or "- 无结构化阻断项，但仍须律师复核。"
    warnings = "\n".join(f"- {item}" for item in result["warnings"]) or "- 无。"
    long_stop = result["long_stop_matrix"]
    return f"""# 并购交易执行矩阵（律师复核底稿）

- 事项编号：{result['matter_id']}
- 核验时点：{result['as_of_date']}
- 结构：{result['structure_gate']['structure_label'] or '未确认'}
- 固定状态：`lawyer_review_required`
- Skill 选择结构：否
- Skill 执行估值、签署、交割或付款：否

## 执行矩阵

| 事项 | 类别 | 责任人 | 状态 | 阻断项 |
|---|---|---|---|---|
{os.linesep.join(rows)}

## 长停日期规则

- 用户确认状态：{long_stop['rule_status']}
- 显式日期：{long_stop['explicit_date'] or '未输入'}
- 日期由 Skill 计算：否
- 状态：{long_stop['status']}

## 全局阻断项

{blockers}

## 告警

{warnings}

本底稿不推荐交易结构，不计算估值，不接受交易条款，不实施签署、交割、过户、付款或监管提交。所有判断及外部行动须由有权人员和执业律师复核并执行。
"""


def write_atomic(result: dict[str, Any], output_dir: Path) -> None:
    if output_dir.exists():
        raise FileExistsError(f"Output directory already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        (temp_dir / "ma-matrix.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (temp_dir / "ma-matrix.md").write_text(render_markdown(result), encoding="utf-8")
        temp_dir.rename(output_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = load_json(args.input)
    validate(data, INPUT_SCHEMA)
    result = build_matrix(data)
    write_atomic(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
