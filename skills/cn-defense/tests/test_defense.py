from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def module():
    spec = importlib.util.spec_from_file_location("cn_defense_build", ROOT / "scripts" / "build_defense.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def example() -> dict:
    return json.loads((ROOT / "examples" / "defense-input.example.json").read_text(encoding="utf-8"))


def test_example_validates_and_preserves_response_states():
    mod = module()
    value = example()
    assert mod.validate_input(value)["ok"]
    result = mod.derive(value)
    assert [x["stance"] for x in result["response_matrix"]] == ["deny", "lack_knowledge"]
    assert result["artifact_state"] == "lawyer_review_required"


def test_missing_response_is_unanswered_never_admit():
    mod = module()
    value = example()
    value["defense_request"]["responses"].pop()
    result = mod.derive(value)
    row = result["response_matrix"][1]
    assert row["stance"] == "unanswered"
    assert row["response_text"] is None
    assert all(x["stance"] != "admit" for x in result["response_matrix"])
    assert result["generation_status"] == "blocked"


def test_response_without_provenance_is_rejected():
    mod = module()
    value = example()
    response = value["defense_request"]["responses"][0]
    response.pop("user_confirmed")
    response.pop("confirmation_note")
    assert not mod.validate_input(value)["ok"]


def test_duplicate_response_for_claim_is_rejected():
    mod = module()
    value = example()
    duplicate = copy.deepcopy(value["defense_request"]["responses"][0])
    duplicate["response_id"] = "RESPONSE-003"
    value["defense_request"]["responses"].append(duplicate)
    result = mod.validate_input(value)
    assert not result["ok"]
    assert any("多个答辩响应" in x for x in result["errors"])


def test_dangling_evidence_is_rejected():
    mod = module()
    value = example()
    value["defense_request"]["responses"][0]["evidence_ids"] = ["EVID-MISSING-001"]
    result = mod.validate_input(value)
    assert not result["ok"]
    assert any("不存在的证据" in x for x in result["errors"])


def test_unresolved_conflict_blocks():
    mod = module()
    value = example()
    value["declared_conflicts"] = [{"conflict_id": "CONFLICT-001", "description": "付款时间存在冲突", "status": "declared", "source_spans": [{"source_id": "SRC-PAYMENT-001", "locator": "凭证第1页", "quote": "日期待核对"}]}]
    result = mod.derive(value)
    assert result["generation_status"] == "blocked"
    assert any(x["code"] == "declared_conflict" for x in result["blockers"])


def test_atomic_build_refuses_overwrite_and_has_no_signature(tmp_path: Path):
    mod = module()
    source = tmp_path / "input.json"
    source.write_text(json.dumps(example(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "out"
    result = mod.build(source, output)
    assert result["generation_status"] == "draft_ready_for_lawyer_review"
    markdown = (output / "民事答辩状-待复核.md").read_text(encoding="utf-8")
    assert "不生成签名或印章" in markdown
    assert "答辩人签章" not in markdown
    with pytest.raises(FileExistsError):
        mod.build(source, output)
