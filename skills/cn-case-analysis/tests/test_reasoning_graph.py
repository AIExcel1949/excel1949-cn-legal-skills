from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_reasoning_graph import build, derive_graph, validate_graph  # noqa: E402
from validate_analysis import load_json  # noqa: E402


@pytest.fixture
def example() -> dict:
    return load_json(ROOT / "examples" / "case-analysis.example.json")


def graph_for(value: dict) -> dict:
    return derive_graph(value, hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest())


def test_graph_contains_only_declared_node_types(example: dict) -> None:
    graph = graph_for(example)
    assert {node["node_type"] for node in graph["nodes"]} <= {
        "party", "claim", "fact", "issue", "evidence", "authority", "position", "element", "risk", "research"
    }
    assert graph["graph_status"] == "derived_from_explicit_links"
    assert graph["conclusion_status"] == "not_generated"


def test_graph_has_no_dangling_edges(example: dict) -> None:
    graph = graph_for(example)
    node_ids = {node["node_id"] for node in graph["nodes"]}
    assert all(edge["from_id"] in node_ids and edge["to_id"] in node_ids for edge in graph["edges"])
    validate_graph(graph, ROOT)


def test_edges_are_non_inferential(example: dict) -> None:
    graph = graph_for(example)
    forbidden = {"supports", "proves", "refutes", "causes", "wins"}
    assert forbidden.isdisjoint({edge["relation"] for edge in graph["edges"]})
    assert all(edge["basis"] == "explicit_input_reference" for edge in graph["edges"])


def test_position_links_match_input(example: dict) -> None:
    graph = graph_for(example)
    first = example["issue_analyses"][0]["positions"][0]
    edges = {(item["from_id"], item["to_id"], item["relation"]) for item in graph["edges"]}
    assert (first["position_id"], first["party_id"], "stated_by") in edges
    for fact_id in first["fact_ids"]:
        assert (first["position_id"], fact_id, "cites_fact") in edges


def test_duplicate_global_identifier_is_rejected(example: dict) -> None:
    value = copy.deepcopy(example)
    value["claims"][0]["claim_id"] = value["parties"][0]["party_id"]
    with pytest.raises(ValueError, match="图节点编号重复"):
        graph_for(value)


def test_build_is_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    source = ROOT / "examples" / "case-analysis.example.json"
    first = tmp_path / "first"
    second = tmp_path / "second"
    build(source, first)
    build(source, second)
    for name in ("reasoning-graph.json", "reasoning-graph.mmd", "validation.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with pytest.raises(FileExistsError):
        build(source, first)
