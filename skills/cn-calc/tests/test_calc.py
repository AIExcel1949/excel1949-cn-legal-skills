from __future__ import annotations

import copy
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from calc_engine import (  # noqa: E402
    CalcError,
    FormulaEvaluator,
    ValueMeta,
    atomic_write_new,
    calculate_report,
    ensure_distinct_from_input,
    render_markdown,
    round_fraction,
)


@pytest.fixture()
def example() -> dict:
    return json.loads((SKILL_DIR / "examples" / "calc-input.example.json").read_text(encoding="utf-8"))


def calculation(report: dict, identifier: str) -> dict:
    return next(item for item in report["calculations"] if item["id"] == identifier)


def test_example_calculates_exactly_and_uses_rounded_prior_results(example: dict) -> None:
    report = calculate_report(example, generated_at="2025-02-10T00:00:00Z")
    assert report["status"] == "calculated_unreviewed"
    assert report["lawyer_reviewed"] is False
    assert report["artifact_role"] == "sidecar_calculation_report"
    assert calculation(report, "period_days")["rounded_value"] == "30"
    assert calculation(report, "interest_amount")["exact_fraction"] == "36000/73"
    assert calculation(report, "interest_amount")["rounded_value"] == "493.15"
    assert calculation(report, "working_total")["exact_fraction"] == "5681941/50"
    assert calculation(report, "working_total")["rounded_value"] == "113638.82"


def test_same_input_and_timestamp_are_deterministic(example: dict) -> None:
    first = calculate_report(example, generated_at="2025-02-10T00:00:00Z")
    second = calculate_report(copy.deepcopy(example), generated_at="2025-02-10T00:00:00Z")
    assert first == second


def test_output_matches_output_schema(example: dict) -> None:
    report = calculate_report(example, generated_at="2025-02-10T00:00:00Z")
    schema = json.loads((SKILL_DIR / "schemas" / "calc-output.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    assert errors == []


@pytest.mark.parametrize(
    ("value", "mode", "expected"),
    [
        (Fraction(5, 2), "HALF_UP", Fraction(3)),
        (Fraction(-5, 2), "HALF_UP", Fraction(-3)),
        (Fraction(5, 2), "HALF_EVEN", Fraction(2)),
        (Fraction(7, 2), "HALF_EVEN", Fraction(4)),
        (Fraction(-12, 10), "DOWN", Fraction(-1)),
        (Fraction(-12, 10), "UP", Fraction(-2)),
        (Fraction(-12, 10), "FLOOR", Fraction(-2)),
        (Fraction(-12, 10), "CEILING", Fraction(-1)),
    ],
)
def test_rounding_modes_are_exact(value: Fraction, mode: str, expected: Fraction) -> None:
    assert round_fraction(value, Fraction(1), mode) == expected


@pytest.mark.parametrize(
    "formula",
    [
        "__import__('os').system('id')",
        "principal.__class__",
        "principal[0]",
        "principal ** 2",
        "[principal][0]",
        "lambda: principal",
        "0.1 * principal",
    ],
)
def test_restricted_formula_rejects_unsafe_or_inexact_syntax(formula: str) -> None:
    evaluator = FormulaEvaluator({"principal": ValueMeta(Fraction(100), "money", "CNY")})
    with pytest.raises(CalcError):
        evaluator.evaluate(formula)


def test_formula_accepts_rational_expression_without_eval() -> None:
    evaluator = FormulaEvaluator({"principal": ValueMeta(Fraction(100), "money", "CNY")})
    result, refs = evaluator.evaluate("principal * (6 / 100) / 365")
    assert result == Fraction(6, 365)
    assert refs == ["principal"]


def test_dimension_mismatch_is_blocked(example: dict) -> None:
    interest = next(item for item in example["calculations"] if item["id"] == "interest_amount")
    interest["formula"] = "principal + annual_rate"
    with pytest.raises(CalcError, match="量纲不一致"):
        calculate_report(example)


def test_unknown_source_is_blocked(example: dict) -> None:
    example["variables"][0]["source_ids"] = ["missing_source"]
    with pytest.raises(CalcError, match="未声明的来源"):
        calculate_report(example)


def test_future_verification_date_is_blocked(example: dict) -> None:
    example["benchmarks"][0]["verified_on"] = "2025-02-11"
    with pytest.raises(CalcError, match="核验日晚于"):
        calculate_report(example)


def test_vague_source_locator_is_blocked(example: dict) -> None:
    example["benchmarks"][0]["locator"] = "待补充"
    with pytest.raises(CalcError, match="缺少具体可回查定位"):
        calculate_report(example)


def test_unconfirmed_input_is_blocked_by_schema(example: dict) -> None:
    example["input_confirmed_by_lawyer"] = False
    with pytest.raises(CalcError, match="Schema"):
        calculate_report(example)


def test_reversed_date_span_is_blocked(example: dict) -> None:
    span = next(item for item in example["variables"] if item["kind"] == "date_span")
    span["start_date"] = "2025-02-02"
    span["end_date"] = "2025-02-01"
    with pytest.raises(CalcError, match="终止日早于起始日"):
        calculate_report(example)


def test_each_date_boundary_combination_is_explicit(example: dict) -> None:
    span = next(item for item in example["variables"] if item["kind"] == "date_span")
    span["start_date"] = "2025-01-01"
    span["end_date"] = "2025-01-02"
    expected = {(True, True): "2/1", (True, False): "1/1", (False, True): "1/1", (False, False): "0/1"}
    for boundaries, exact in expected.items():
        span["include_start"], span["include_end"] = boundaries
        report = calculate_report(example)
        trace = next(item for item in report["variables"] if item["id"] == "interest_days")
        assert trace["exact_fraction"] == exact


def test_currency_mismatch_is_blocked(example: dict) -> None:
    example["variables"][0]["currency"] = "USD"
    with pytest.raises(CalcError, match="币种不一致"):
        calculate_report(example)


def test_quantity_cannot_consume_money(example: dict) -> None:
    example["calculations"][0]["formula"] = "principal"
    with pytest.raises(CalcError, match="公式量纲为 money"):
        calculate_report(example)


def test_forward_reference_is_blocked(example: dict) -> None:
    example["calculations"][0]["formula"] = "interest_amount"
    with pytest.raises(CalcError, match="未声明或不可用的名称"):
        calculate_report(example)


def test_duplicate_ids_are_blocked(example: dict) -> None:
    example["calculations"][0]["id"] = example["variables"][0]["id"]
    with pytest.raises(CalcError, match="ID 重复"):
        calculate_report(example)


def test_atomic_writer_creates_both_and_refuses_overwrite(tmp_path: Path) -> None:
    json_path = tmp_path / "result.json"
    md_path = tmp_path / "result.md"
    atomic_write_new({json_path: b"{}\n", md_path: b"# report\n"})
    assert json_path.read_bytes() == b"{}\n"
    assert md_path.read_bytes() == b"# report\n"
    with pytest.raises(CalcError, match="拒绝覆盖"):
        atomic_write_new({json_path: b"changed", tmp_path / "new.md": b"new"})
    assert json_path.read_bytes() == b"{}\n"
    assert not (tmp_path / "new.md").exists()


def test_output_cannot_equal_input(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    with pytest.raises(CalcError, match="不得与输入相同"):
        ensure_distinct_from_input(input_path, [input_path])


def test_cli_creates_json_and_markdown_then_refuses_overwrite(example: dict, tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    json_path = tmp_path / "result.json"
    md_path = tmp_path / "result.md"
    input_path.write_text(json.dumps(example, ensure_ascii=False), encoding="utf-8")
    command = [
        sys.executable,
        str(SCRIPTS_DIR / "calculate.py"),
        str(input_path),
        "--json-output",
        str(json_path),
        "--markdown-output",
        str(md_path),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["artifact_role"] == "sidecar_calculation_report"
    assert "不会自动回填诉请" in md_path.read_text(encoding="utf-8")
    before = json_path.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode == 1
    assert "拒绝覆盖" in second.stderr
    assert json_path.read_bytes() == before


def test_markdown_exposes_sources_formula_and_rounding(example: dict) -> None:
    report = calculate_report(example, generated_at="2025-02-10T00:00:00Z")
    markdown = render_markdown(report)
    assert "contract_rate" in markdown
    assert "principal * annual_rate * interest_days / year_basis" in markdown
    assert "0.01 / HALF_UP" in markdown
    assert "计入起日：否" in markdown
    assert "计入止日：是" in markdown
