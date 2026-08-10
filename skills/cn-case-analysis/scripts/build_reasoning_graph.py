#!/usr/bin/env python3
"""从案件分析输入的显式稳定编号关系生成只读关系溯源图。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from validate_analysis import load_json, validate


NODE_LABEL_FIELDS = {
    "party": "name",
    "claim": "text_verbatim",
    "fact": "raw_value",
    "issue": "question",
    "evidence": "name",
    "authority": "title",
    "position": "statement",
    "element": "name",
    "risk": "description",
    "research": "question",
}


def _node(node_id: str, node_type: str, value: dict[str, Any], status: str) -> dict[str, str]:
    label = str(value.get(NODE_LABEL_FIELDS[node_type], node_id)).strip() or node_id
    return {"node_id": node_id, "node_type": node_type, "label": label, "working_status": status}


def derive_graph(value: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_node(node_id: str, node_type: str, item: dict[str, Any], status: str) -> None:
        if node_id in nodes:
            raise ValueError(f"图节点编号重复：{node_id}")
        nodes[node_id] = _node(node_id, node_type, item, status)

    def add_edge(from_id: str, to_id: str, relation: str) -> None:
        if from_id not in nodes or to_id not in nodes:
            raise ValueError(f"关系图存在悬空边：{from_id} --{relation}--> {to_id}")
        key = (from_id, to_id, relation)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({
            "edge_id": f"EDGE-{len(edges) + 1:04d}",
            "from_id": from_id,
            "to_id": to_id,
            "relation": relation,
            "basis": "explicit_input_reference",
        })

    for item in value["parties"]:
        add_node(item["party_id"], "party", item, item["name_status"])
    for item in value["claims"]:
        add_node(item["claim_id"], "claim", item, item["status"])
    for item in value["facts"]:
        add_node(item["fact_id"], "fact", item, item["status"])
    for item in value["issues"]:
        add_node(item["issue_id"], "issue", item, item["status"])
    for item in value["evidence"]:
        add_node(item["evidence_id"], "evidence", item, item["verification_status"])
    for item in value["authorities"]:
        add_node(item["authority_id"], "authority", item, item["effect_status"])

    for analysis in value["issue_analyses"]:
        issue_id = analysis["issue_id"]
        for item in analysis["positions"]:
            add_node(item["position_id"], "position", item, item["position_type"])
        for item in analysis["elements"]:
            add_node(item["element_id"], "element", item, item["status"])
        for item in analysis["risks"]:
            add_node(item["risk_id"], "risk", item, item["level"])
        for item in analysis["research_items"]:
            add_node(item["research_id"], "research", item, item["status"])

    for analysis in value["issue_analyses"]:
        issue_id = analysis["issue_id"]
        if analysis["parent_issue_id"] is not None:
            add_edge(issue_id, analysis["parent_issue_id"], "sub_issue_of")
        for claim_id in analysis["claim_ids"]:
            add_edge(issue_id, claim_id, "examines_claim")
        for item in analysis["positions"]:
            position_id = item["position_id"]
            add_edge(position_id, issue_id, "position_on")
            add_edge(position_id, item["party_id"], "stated_by")
            for fact_id in item["fact_ids"]:
                add_edge(position_id, fact_id, "cites_fact")
            for evidence_id in item["evidence_ids"]:
                add_edge(position_id, evidence_id, "cites_evidence")
            for authority_id in item["authority_ids"]:
                add_edge(position_id, authority_id, "cites_authority")
        for item in analysis["elements"]:
            element_id = item["element_id"]
            add_edge(element_id, issue_id, "element_of")
            for party_id in item["burden_party_ids"]:
                add_edge(element_id, party_id, "burden_recorded_for")
            for fact_id in item["fact_ids"]:
                add_edge(element_id, fact_id, "linked_fact")
            for evidence_id in item["evidence_ids"]:
                add_edge(element_id, evidence_id, "linked_evidence")
            for authority_id in item["authority_ids"]:
                add_edge(element_id, authority_id, "linked_authority")
        for item in analysis["risks"]:
            add_edge(item["risk_id"], issue_id, "risk_on")
        for item in analysis["research_items"]:
            add_edge(item["research_id"], issue_id, "research_for")

    return {
        "schema_version": "1.0",
        "analysis_id": value["analysis_id"],
        "matter_id": value["matter_id"],
        "source_sha256": source_sha256,
        "graph_status": "derived_from_explicit_links",
        "conclusion_status": "not_generated",
        "nodes": sorted(nodes.values(), key=lambda item: (item["node_type"], item["node_id"])),
        "edges": sorted(edges, key=lambda item: (item["from_id"], item["to_id"], item["relation"])),
    }


def validate_graph(graph: dict[str, Any], root: Path) -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((root / "schemas" / "reasoning-graph.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(graph), key=lambda item: tuple(str(part) for part in item.absolute_path))
    if errors:
        raise ValueError("关系图 Schema 校验失败：" + "；".join(error.message for error in errors))
    node_ids = {item["node_id"] for item in graph["nodes"]}
    if len(node_ids) != len(graph["nodes"]):
        raise ValueError("关系图节点编号重复")
    for edge in graph["edges"]:
        if edge["from_id"] not in node_ids or edge["to_id"] not in node_ids:
            raise ValueError(f"关系图存在悬空边：{edge['edge_id']}")


def _mermaid_id(node_id: str) -> str:
    return "N" + hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:12]


def _safe_label(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    compact = compact.replace("\\", "／").replace('"', "”").replace("`", "｀")
    return compact[:80] + ("…" if len(compact) > 80 else "")


def mermaid(graph: dict[str, Any]) -> str:
    lines = ["flowchart LR"]
    for node in graph["nodes"]:
        label = _safe_label(f"{node['node_type']}｜{node['label']}｜{node['working_status']}")
        lines.append(f"  {_mermaid_id(node['node_id'])}[\"{label}\"]")
    for edge in graph["edges"]:
        lines.append(f"  {_mermaid_id(edge['from_id'])} -- \"{edge['relation']}\" --> {_mermaid_id(edge['to_id'])}")
    lines.extend([
        "  classDef default fill:#F5F9F6,stroke:#1F8A4F,color:#1F1F1F;",
        "  linkStyle default stroke:#0F5A33,color:#6B6B6B;",
    ])
    return "\n".join(lines) + "\n"


def build(input_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    raw = input_path.read_bytes()
    value = load_json(input_path)
    root = Path(__file__).resolve().parent.parent
    validation = validate(value, root)
    if not validation["ok"]:
        raise ValueError("；".join(validation["errors"]))
    graph = derive_graph(value, hashlib.sha256(raw).hexdigest())
    validate_graph(graph, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-reasoning-graph-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        (temp / "reasoning-graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "reasoning-graph.mmd").write_text(mermaid(graph), encoding="utf-8")
        (temp / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成案件关系溯源图")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.input, args.output)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] 已生成案件关系溯源图：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
