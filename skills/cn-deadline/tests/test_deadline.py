from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from calculate_deadline import write_new_atomic  # noqa: E402
from deadline_lib import InputError, calculate, load_json, validate_input  # noqa: E402


EXAMPLE = SKILL_DIR / "examples" / "internal-review.example.json"
BLOCKED_EXAMPLE = SKILL_DIR / "examples" / "unverified-rule-blocked.example.json"


def load_example(path: Path = EXAMPLE):
    return load_json(path)


def test_working_day_example_is_deterministic():
    data, raw = load_example()
    result = calculate(data, raw)
    deadline = result["results"][0]
    assert deadline["status"] == "calculated"
    assert deadline["deadline_date"] == "2026-07-20"
    assert deadline["deadline_at"] == "2026-07-20T18:00:00+08:00"
    assert [step["operation"] for step in deadline["steps"]] == ["counted_days", "next_working_day"]


def test_unverified_rule_blocks_without_fake_date():
    data, raw = load_example(BLOCKED_EXAMPLE)
    deadline = calculate(data, raw)["results"][0]
    assert deadline["status"] == "blocked"
    assert "deadline_date" not in deadline
    assert "deadline_at" not in deadline
    assert deadline["steps"] == []
    assert any("unknown" in blocker for blocker in deadline["blockers"])


def test_anniversary_invalid_day_can_block():
    data, raw = load_example()
    deadline = data["deadlines"][0]
    deadline["event"]["operative_date"] = "2026-01-31"
    deadline["event"].pop("occurred_at")
    deadline["rule"]["calculation"] = {
        "method": "anniversary",
        "unit": "months",
        "count": 1,
        "invalid_day_policy": "block",
    }
    deadline["rule"]["non_working_expiry"] = "keep"
    deadline["rule"].pop("calendar_id")
    result = calculate(data, json.dumps(data).encode("utf-8"))["results"][0]
    assert result["status"] == "blocked"
    assert any("不存在 31 日" in blocker for blocker in result["blockers"])


def test_anniversary_can_use_explicit_last_day_policy():
    data, _ = load_example()
    deadline = data["deadlines"][0]
    deadline["event"]["operative_date"] = "2026-01-31"
    deadline["event"].pop("occurred_at")
    deadline["rule"]["calculation"] = {
        "method": "anniversary",
        "unit": "months",
        "count": 1,
        "invalid_day_policy": "last_day_of_month",
    }
    deadline["rule"]["non_working_expiry"] = "keep"
    deadline["rule"].pop("calendar_id")
    result = calculate(data, json.dumps(data).encode("utf-8"))["results"][0]
    assert result["status"] == "calculated"
    assert result["deadline_date"] == "2026-02-28"


def test_calendar_coverage_shortage_blocks_and_discards_partial_steps():
    data, _ = load_example()
    data["calendars"][0]["coverage_end"] = "2026-07-17"
    data["calendars"][0]["working_dates"] = []
    result = calculate(data, json.dumps(data).encode("utf-8"))["results"][0]
    assert result["status"] == "blocked"
    assert result["steps"] == []
    assert any("超出日历" in blocker for blocker in result["blockers"])


def test_future_verification_date_blocks():
    data, _ = load_example()
    data["deadlines"][0]["rule"]["source"]["verified_on"] = "2026-07-19"
    result = calculate(data, json.dumps(data).encode("utf-8"))["results"][0]
    assert result["status"] == "blocked"
    assert any("晚于计算基准日" in blocker for blocker in result["blockers"])


def test_duplicate_calendar_dates_are_rejected():
    data, _ = load_example()
    data["calendars"][0]["working_dates"] = ["2026-07-15"]
    with pytest.raises(InputError, match="重叠"):
        validate_input(data)


def test_missing_add_days_fields_are_rejected():
    data, _ = load_example()
    source = copy.deepcopy(data["deadlines"][0]["rule"]["source"])
    source["source_id"] = "SRC-ADJUSTMENT-DEMO-001"
    data["deadlines"][0]["adjustments"] = [
        {
            "adjustment_id": "ADJ-DEMO-001",
            "type": "add_days",
            "reason": "教学示例",
            "source": source,
        }
    ]
    with pytest.raises(InputError, match="count"):
        validate_input(data)


def test_atomic_writer_refuses_existing_output(tmp_path: Path):
    output = tmp_path / "result.json"
    write_new_atomic(output, b"first\n")
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        write_new_atomic(output, b"second\n")
    assert output.read_bytes() == b"first\n"


def test_duplicate_json_keys_are_rejected(tmp_path: Path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
    with pytest.raises(InputError, match="重复 JSON 键"):
        load_json(path)
