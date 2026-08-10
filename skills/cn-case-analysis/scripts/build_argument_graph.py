#!/usr/bin/env python3
"""校验并编排可回查的法律论证图，不自动判定最优观点或胜败。"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from validate_analysis import load_json, validate


ROOT = Path(__file__).resolve().parent.parent
CONSTRUCTIVE_RELATIONS = {"supports", "depends_on", "qualifies"}
ATTACK_RELATIONS = {"attacks", "defeats"}
LIMITATIONS = [
    "论证图只编排已登记节点和关系，不证明事实真实、证据可采或法律适用正确。",
    "置信度只能来自用户声明或律师评估，脚本不根据论据数量自动评分。",
    "竞争性假设不得被改写为已确认事实，结论仍须执业律师独立判断。",
]


def schema_errors(value: dict[str, Any], name: str) -> list[str]:
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    return [
        f"Schema {'.'.join(str(part) for part in error.absolute_path) or '<root>'}：{error.message}"
        for error in sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
    ]


def unique_index(items: list[dict[str, Any]], key: str, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        identity = item[key]
        if identity in result:
            errors.append(f"{label}编号重复：{identity}")
        else:
            result[identity] = item
    return result


def check_refs(owner: str, label: str, values: list[str], allowed: set[str], errors: list[str]) -> None:
    missing = sorted(set(values) - allowed)
    if missing:
        errors.append(f"{owner} 引用不存在的{label}：{'、'.join(missing)}")


def topological_layers(nodes: set[str], edges: list[dict[str, Any]], errors: list[str]) -> list[list[str]]:
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {node_id: 0 for node_id in nodes}
    for edge in edges:
        if edge["relation"] not in CONSTRUCTIVE_RELATIONS or edge["status"] == "rejected":
            continue
        source, target = edge["from_node_id"], edge["to_node_id"]
        if target not in outgoing[source]:
            outgoing[source].add(target)
            indegree[target] += 1
    available = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    layers: list[list[str]] = []
    visited = 0
    while available:
        layer = available
        layers.append(layer)
        visited += len(layer)
        next_nodes: list[str] = []
        for source in layer:
            for target in sorted(outgoing[source]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    next_nodes.append(target)
        available = sorted(next_nodes)
    if visited != len(nodes):
        errors.append("支持、依赖或限定关系存在环，无法形成可回查的论证顺序")
    return layers


def derive(analysis: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    errors = schema_errors(graph, "argument-graph.schema.json")
    analysis_validation = validate(analysis, ROOT)
    errors.extend(analysis_validation["errors"])
    if graph.get("analysis_id") != analysis.get("analysis_id"):
        errors.append("论证图 analysis_id 与案件分析输入不一致")
    if graph.get("matter_id") != analysis.get("matter_id"):
        errors.append("论证图 matter_id 与案件分析输入不一致")
    if errors:
        raise ValueError("；".join(errors))

    nodes = unique_index(graph["nodes"], "node_id", "论证节点", errors)
    edges = unique_index(graph["edges"], "edge_id", "论证边", errors)
    tests = unique_index(graph["hypothesis_tests"], "test_id", "假设检验", errors)
    node_ids = set(nodes)
    issue_ids = {item["issue_id"] for item in analysis["issues"]}
    fact_ids = {item["fact_id"] for item in analysis["facts"]}
    evidence_ids = {item["evidence_id"] for item in analysis["evidence"]}
    authority_ids = {item["authority_id"] for item in analysis["authorities"]}

    for node in graph["nodes"]:
        owner = node["node_id"]
        check_refs(owner, "争点", [node["issue_id"]], issue_ids, errors)
        check_refs(owner, "事实", node["fact_ids"], fact_ids, errors)
        check_refs(owner, "证据", node["evidence_ids"], evidence_ids, errors)
        check_refs(owner, "法源", node["authority_ids"], authority_ids, errors)
        if node["confidence"] != "unassessed" and node["confidence_source"] == "not_scored":
            errors.append(f"{owner} 的置信度没有用户声明或律师评估来源")

    for edge in graph["edges"]:
        owner = edge["edge_id"]
        check_refs(owner, "论证节点", [edge["from_node_id"], edge["to_node_id"]], node_ids, errors)
        if edge["from_node_id"] == edge["to_node_id"]:
            errors.append(f"{owner} 不得指向自身")

    layers = topological_layers(node_ids, graph["edges"], errors)
    for test in graph["hypothesis_tests"]:
        owner = test["test_id"]
        all_refs = [test["hypothesis_node_id"], *test["supporting_node_ids"], *test["contradicting_node_ids"]]
        check_refs(owner, "论证节点", all_refs, node_ids, errors)
        hypothesis = nodes.get(test["hypothesis_node_id"])
        if hypothesis and hypothesis["node_type"] != "alternative_hypothesis":
            errors.append(f"{owner} 的待检验节点不是竞争性假设")
    if errors:
        raise ValueError("；".join(errors))

    active_edges = [edge for edge in graph["edges"] if edge["status"] != "rejected"]
    incoming_support = {edge["to_node_id"] for edge in active_edges if edge["relation"] in CONSTRUCTIVE_RELATIONS}
    unsupported_conclusions = sorted(
        node_id for node_id, node in nodes.items()
        if node["node_type"] == "conclusion" and node_id not in incoming_support
    )
    answered_attackers = {
        edge["to_node_id"] for edge in active_edges
        if edge["relation"] in ATTACK_RELATIONS and nodes[edge["from_node_id"]]["node_type"] == "rebuttal"
    }
    unanswered_attacks = [
        edge for edge in active_edges
        if edge["relation"] in ATTACK_RELATIONS
        and nodes[edge["from_node_id"]]["node_type"] == "objection"
        and edge["from_node_id"] not in answered_attackers
    ]
    result = {
        "schema_version": "1.0",
        "graph_id": graph["graph_id"],
        "analysis_id": graph["analysis_id"],
        "matter_id": graph["matter_id"],
        "validation_state": "machine_checked",
        "argument_state": "lawyer_review_required",
        "nodes": sorted(graph["nodes"], key=lambda item: item["node_id"]),
        "edges": sorted(graph["edges"], key=lambda item: item["edge_id"]),
        "topological_layers": layers,
        "unsupported_conclusions": unsupported_conclusions,
        "unanswered_attacks": sorted(unanswered_attacks, key=lambda item: item["edge_id"]),
        "hypothesis_tests": sorted(graph["hypothesis_tests"], key=lambda item: item["test_id"]),
        "limitations": LIMITATIONS,
    }
    output_errors = schema_errors(result, "argument-graph-output.schema.json")
    if output_errors:
        raise ValueError("；".join(output_errors))
    return result


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成中立、可回查的法律论证图")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("graph", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = derive(load_json(args.analysis), load_json(args.graph))
    atomic_write(args.output, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
