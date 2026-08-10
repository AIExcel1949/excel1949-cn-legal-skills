from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

from build_argument_graph import atomic_write, derive  # noqa: E402
from validate_analysis import load_json  # noqa: E402


@pytest.fixture
def analysis():
    return load_json(SKILL / "examples" / "case-analysis.example.json")


@pytest.fixture
def graph():
    nodes = [
        {"node_id": "ARG-fact", "issue_id": "ISSUE-payment", "node_type": "fact_premise", "statement": "材料记载已交付。", "status": "declared", "fact_ids": ["FACT-delivery"], "evidence_ids": ["EVID-delivery"], "authority_ids": [], "confidence": "unassessed", "confidence_source": "not_scored"},
        {"node_id": "ARG-conclusion", "issue_id": "ISSUE-payment", "node_type": "conclusion", "statement": "付款请求是否成立待律师判断。", "status": "ai_proposed", "fact_ids": [], "evidence_ids": [], "authority_ids": [], "confidence": "unassessed", "confidence_source": "not_scored"},
        {"node_id": "ARG-objection", "issue_id": "ISSUE-quality-defense", "node_type": "objection", "statement": "对方主张存在质量问题。", "status": "declared", "fact_ids": ["FACT-quality-notice"], "evidence_ids": ["EVID-quality-chat"], "authority_ids": [], "confidence": "unassessed", "confidence_source": "not_scored"},
        {"node_id": "ARG-rebuttal", "issue_id": "ISSUE-quality-defense", "node_type": "rebuttal", "statement": "质量异议的时间与内容仍待核实。", "status": "ai_proposed", "fact_ids": ["FACT-quality-notice"], "evidence_ids": ["EVID-quality-chat"], "authority_ids": [], "confidence": "unassessed", "confidence_source": "not_scored"},
        {"node_id": "ARG-hypothesis", "issue_id": "ISSUE-quality-defense", "node_type": "alternative_hypothesis", "statement": "材料也可能支持其他事实解释。", "status": "ai_proposed", "fact_ids": [], "evidence_ids": ["EVID-quality-chat"], "authority_ids": [], "confidence": "unassessed", "confidence_source": "not_scored"},
    ]
    return {
        "schema_version": "1.0", "graph_id": "GRAPH-001", "analysis_id": "ANALYSIS-2026-001", "matter_id": "MATTER-2026-001", "nodes": nodes,
        "edges": [
            {"edge_id": "EDGE-support", "from_node_id": "ARG-fact", "to_node_id": "ARG-conclusion", "relation": "supports", "status": "ai_proposed"},
            {"edge_id": "EDGE-attack", "from_node_id": "ARG-objection", "to_node_id": "ARG-conclusion", "relation": "attacks", "status": "declared"},
            {"edge_id": "EDGE-rebut", "from_node_id": "ARG-rebuttal", "to_node_id": "ARG-objection", "relation": "attacks", "status": "ai_proposed"},
        ],
        "hypothesis_tests": [{"test_id": "TEST-001", "hypothesis_node_id": "ARG-hypothesis", "supporting_node_ids": ["ARG-objection"], "contradicting_node_ids": ["ARG-rebuttal"], "falsification_conditions": ["取得能排除该解释的完整原始记录。"], "missing_information": ["沟通记录的完整上下文。"]}],
    }


def test_argument_graph_keeps_positions_and_attacks_separate(analysis, graph):
    result = derive(analysis, graph)
    assert result["argument_state"] == "lawyer_review_required"
    assert result["unsupported_conclusions"] == []
    assert result["unanswered_attacks"] == []
    assert result["topological_layers"]


def test_dangling_fact_reference_is_rejected(analysis, graph):
    graph["nodes"][0]["fact_ids"] = ["FACT-not-found"]
    with pytest.raises(ValueError, match="不存在的事实"):
        derive(analysis, graph)


def test_constructive_cycle_is_rejected(analysis, graph):
    graph["edges"].append({"edge_id": "EDGE-cycle", "from_node_id": "ARG-conclusion", "to_node_id": "ARG-fact", "relation": "depends_on", "status": "declared"})
    with pytest.raises(ValueError, match="存在环"):
        derive(analysis, graph)


def test_machine_cannot_invent_confidence_score(analysis, graph):
    graph["nodes"][0]["confidence"] = "high"
    with pytest.raises(ValueError, match="置信度"):
        derive(analysis, graph)


def test_hypothesis_test_must_target_alternative_hypothesis(analysis, graph):
    graph["hypothesis_tests"][0]["hypothesis_node_id"] = "ARG-conclusion"
    with pytest.raises(ValueError, match="不是竞争性假设"):
        derive(analysis, graph)


def test_unanswered_attack_and_unsupported_conclusion_are_exposed(analysis, graph):
    graph["edges"] = [graph["edges"][1]]
    result = derive(analysis, graph)
    assert result["unsupported_conclusions"] == ["ARG-conclusion"]
    assert result["unanswered_attacks"][0]["edge_id"] == "EDGE-attack"


def test_output_is_deterministic_and_non_overwriting(analysis, graph, tmp_path):
    result = derive(analysis, graph)
    assert result == derive(copy.deepcopy(analysis), copy.deepcopy(graph))
    output = tmp_path / "argument-graph.json"
    atomic_write(output, result)
    assert json.loads(output.read_text(encoding="utf-8"))["graph_id"] == "GRAPH-001"
    with pytest.raises(FileExistsError):
        atomic_write(output, result)
