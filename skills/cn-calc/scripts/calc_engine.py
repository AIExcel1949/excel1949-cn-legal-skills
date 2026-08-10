#!/usr/bin/env python3
"""中国律师案件确定性计算引擎。"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


ENGINE_VERSION = "1.0.0"
DISCLAIMER = (
    "AI 生成的计算报告仅供学习和办案辅助参考，"
    "必须由专业执业律师逐项核验，不得直接提交法院、"
    "仲裁机构或对方当事人。"
)
DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)(?:\.([0-9]+))?$")
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_AST_NODES = 128
MAX_INTEGER_DIGITS = 50
MAX_RESULT_BITS = 4096
VAGUE_LOCATORS = {"法律", "网络", "合同", "证据", "文件", "法院", "系统", "待补充", "不详"}


class CalcError(ValueError):
    """可向用户报告的输入或计算错误。"""


@dataclass(frozen=True)
class ValueMeta:
    value: Fraction
    unit: str
    currency: str | None = None


Dimension = tuple[tuple[str, int], ...]


def dimension_for_unit(unit: str) -> Dimension:
    normalized = "day" if unit == "calendar_day" else unit
    if normalized == "ratio":
        return ()
    return ((normalized, 1),)


def combine_dimensions(left: Dimension, right: Dimension, direction: int) -> Dimension:
    powers = dict(left)
    for unit, power in right:
        powers[unit] = powers.get(unit, 0) + direction * power
    return tuple(sorted((unit, power) for unit, power in powers.items() if power))


def dimension_text(dimension: Dimension) -> str:
    if not dimension:
        return "ratio"
    return " * ".join(unit if power == 1 else f"{unit}^{power}" for unit, power in dimension)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "calc-input.schema.json"


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CalcError(f"无法读取输入文件：{exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CalcError(f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列") from exc
    if not isinstance(data, dict):
        raise CalcError("输入 JSON 顶层必须是对象。")
    return data


def validate_schema(data: dict[str, Any]) -> None:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))
    if errors:
        messages: list[str] = []
        for error in errors[:20]:
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            messages.append(f"{location}: {error.message}")
        suffix = "" if len(errors) <= 20 else f"\n其余 {len(errors) - 20} 项错误已省略。"
        raise CalcError("输入不符合 Schema：\n" + "\n".join(messages) + suffix)


def decimal_to_fraction(text: str) -> Fraction:
    match = DECIMAL_RE.fullmatch(text)
    if not match:
        raise CalcError(f"非法十进制字面量：{text}")
    negative = text.startswith("-")
    unsigned = text[1:] if negative else text
    integer, dot, fractional = unsigned.partition(".")
    if dot:
        numerator = int(integer + fractional)
        denominator = 10 ** len(fractional)
    else:
        numerator = int(integer)
        denominator = 1
    return Fraction(-numerator if negative else numerator, denominator)


def fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def decimal_preview(value: Fraction, digits: int = 30) -> str:
    with localcontext() as context:
        context.prec = max(50, digits + 20)
        rendered = format(Decimal(value.numerator) / Decimal(value.denominator), f".{digits}f")
    return rendered.rstrip("0").rstrip(".") or "0"


def _trunc_toward_zero(value: Fraction) -> int:
    if value >= 0:
        return value.numerator // value.denominator
    return -((-value.numerator) // value.denominator)


def _round_integer(value: Fraction, mode: str) -> int:
    floor_value = value.numerator // value.denominator
    ceiling_value = -((-value.numerator) // value.denominator)
    if mode == "FLOOR":
        return floor_value
    if mode == "CEILING":
        return ceiling_value
    if mode == "DOWN":
        return _trunc_toward_zero(value)
    if mode == "UP":
        truncated = _trunc_toward_zero(value)
        return truncated if value.denominator == 1 else truncated + (1 if value > 0 else -1)

    lower = floor_value
    remainder = value - lower
    doubled = remainder * 2
    if doubled < 1:
        return lower
    if doubled > 1:
        return lower + 1
    if mode == "HALF_UP":
        return lower + 1 if value >= 0 else lower
    if mode == "HALF_EVEN":
        return lower if lower % 2 == 0 else lower + 1
    raise CalcError(f"不支持的舍入模式：{mode}")


def round_fraction(value: Fraction, quantum: Fraction, mode: str) -> Fraction:
    if quantum <= 0:
        raise CalcError("舍入量级必须大于零。")
    return Fraction(_round_integer(value / quantum, mode), 1) * quantum


def format_rounded(value: Fraction, quantum_text: str) -> str:
    decimals = len(quantum_text.partition(".")[2]) if "." in quantum_text else 0
    with localcontext() as context:
        context.prec = max(100, len(str(abs(value.numerator))) + decimals + 20)
        result = Decimal(value.numerator) / Decimal(value.denominator)
        return format(result, f".{decimals}f")


class FormulaEvaluator:
    """不使用 eval 的受限算术表达式求值器。"""

    def __init__(self, environment: dict[str, ValueMeta]):
        self.environment = environment
        self.references: set[str] = set()
        self.dimension: Dimension = ()

    def evaluate(self, formula: str) -> tuple[Fraction, list[str]]:
        self.references = set()
        self.dimension = ()
        if len(formula) > 512:
            raise CalcError("公式长度超过 512 个字符。")
        try:
            tree = ast.parse(formula, mode="eval")
        except SyntaxError as exc:
            raise CalcError(f"公式语法错误：{exc.msg}") from exc
        if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
            raise CalcError(f"公式节点超过 {MAX_AST_NODES} 个。")
        value, self.dimension = self._visit(tree.body)
        self._check_size(value)
        return value, sorted(self.references)

    def _visit(self, node: ast.AST) -> tuple[Fraction, Dimension]:
        if isinstance(node, ast.Name):
            if not IDENTIFIER_RE.fullmatch(node.id) or node.id not in self.environment:
                raise CalcError(f"公式引用了未声明或不可用的名称：{node.id}")
            self.references.add(node.id)
            meta = self.environment[node.id]
            return meta.value, dimension_for_unit(meta.unit)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int):
                raise CalcError("公式中只允许整数常量；小数应放入带来源的变量。")
            if len(str(abs(node.value))) > MAX_INTEGER_DIGITS:
                raise CalcError(f"整数常量超过 {MAX_INTEGER_DIGITS} 位。")
            return Fraction(node.value, 1), ()
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand, dimension = self._visit(node.operand)
            return (operand if isinstance(node.op, ast.UAdd) else -operand), dimension
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, left_dimension = self._visit(node.left)
            right, right_dimension = self._visit(node.right)
            if isinstance(node.op, ast.Add):
                if left_dimension != right_dimension:
                    raise CalcError(
                        f"加法两侧量纲不一致：{dimension_text(left_dimension)} 与 {dimension_text(right_dimension)}"
                    )
                result = left + right
                result_dimension = left_dimension
            elif isinstance(node.op, ast.Sub):
                if left_dimension != right_dimension:
                    raise CalcError(
                        f"减法两侧量纲不一致：{dimension_text(left_dimension)} 与 {dimension_text(right_dimension)}"
                    )
                result = left - right
                result_dimension = left_dimension
            elif isinstance(node.op, ast.Mult):
                result = left * right
                result_dimension = combine_dimensions(left_dimension, right_dimension, 1)
            else:
                if right == 0:
                    raise CalcError("公式存在除以零。")
                result = left / right
                result_dimension = combine_dimensions(left_dimension, right_dimension, -1)
            self._check_size(result)
            return result, result_dimension
        raise CalcError(f"公式包含未允许的语法：{type(node).__name__}")

    @staticmethod
    def _check_size(value: Fraction) -> None:
        if value.numerator.bit_length() > MAX_RESULT_BITS or value.denominator.bit_length() > MAX_RESULT_BITS:
            raise CalcError("中间结果过大，计算已阻断。")


def _ensure_unique(items: Iterable[dict[str, Any]], label: str, occupied: set[str] | None = None) -> set[str]:
    seen = set() if occupied is None else set(occupied)
    local: set[str] = set()
    for item in items:
        identifier = item["id"]
        if identifier in seen:
            raise CalcError(f"{label} ID 重复或与其他 ID 冲突：{identifier}")
        seen.add(identifier)
        local.add(identifier)
    return local


def _validate_sources(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source_ids = _ensure_unique(data["benchmarks"], "来源")
    sources = {item["id"]: item for item in data["benchmarks"]}
    as_of = date.fromisoformat(data["as_of_date"])
    for source in data["benchmarks"]:
        if source["locator"].strip() in VAGUE_LOCATORS or not source["quote"].strip():
            raise CalcError(f"来源 {source['id']} 缺少具体可回查定位或有效原文摘录。")
        if date.fromisoformat(source["verified_on"]) > as_of:
            raise CalcError(f"来源 {source['id']} 的核验日晚于计算基准日。")
    for item in [*data["variables"], *data["calculations"]]:
        unknown = sorted(set(item["source_ids"]) - source_ids)
        if unknown:
            raise CalcError(f"{item['id']} 引用了未声明的来源：{', '.join(unknown)}")
    return sources


def _variable_value(item: dict[str, Any]) -> tuple[ValueMeta, dict[str, Any]]:
    kind = item["kind"]
    trace: dict[str, Any] = {
        "id": item["id"],
        "label": item["label"],
        "kind": kind,
        "unit": item["unit"],
        "source_ids": item["source_ids"],
    }
    if kind == "decimal":
        value = decimal_to_fraction(item["value"])
        trace["input_value"] = item["value"]
    elif kind == "rational":
        value = Fraction(int(item["numerator"]), int(item["denominator"]))
        trace["input_numerator"] = item["numerator"]
        trace["input_denominator"] = item["denominator"]
    else:
        start = date.fromisoformat(item["start_date"])
        end = date.fromisoformat(item["end_date"])
        if end < start:
            raise CalcError(f"期间变量 {item['id']} 的终止日早于起始日。")
        days = (end - start).days + 1 - (0 if item["include_start"] else 1) - (0 if item["include_end"] else 1)
        value = Fraction(max(days, 0), 1)
        trace["period_trace"] = {
            "start_date": item["start_date"],
            "end_date": item["end_date"],
            "include_start": item["include_start"],
            "include_end": item["include_end"],
            "calendar_days": str(value.numerator),
        }
    currency = item.get("currency")
    if currency is not None:
        trace["currency"] = currency
    trace["exact_fraction"] = fraction_text(value)
    return ValueMeta(value=value, unit=item["unit"], currency=currency), trace


def canonical_input_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def calculate_report(data: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    validate_schema(data)
    _validate_sources(data)

    variable_ids = _ensure_unique(data["variables"], "变量")
    _ensure_unique(data["calculations"], "计算项", variable_ids)

    environment: dict[str, ValueMeta] = {}
    variable_traces: list[dict[str, Any]] = []
    for item in data["variables"]:
        meta, trace = _variable_value(item)
        environment[item["id"]] = meta
        variable_traces.append(trace)

    calculation_traces: list[dict[str, Any]] = []
    for item in data["calculations"]:
        evaluator = FormulaEvaluator(environment)
        try:
            exact, references = evaluator.evaluate(item["formula"])
        except CalcError as exc:
            raise CalcError(f"计算项 {item['id']} 失败：{exc}") from exc

        money_references = [name for name in references if environment[name].unit == "money"]
        expected_dimension = dimension_for_unit("money" if item["result_type"] == "money" else item["unit"])
        if evaluator.dimension != expected_dimension:
            raise CalcError(
                f"计算项 {item['id']} 的公式量纲为 {dimension_text(evaluator.dimension)}，"
                f"但声明结果量纲为 {dimension_text(expected_dimension)}。"
            )
        if item["result_type"] == "money":
            mismatched = [name for name in money_references if environment[name].currency != item["currency"]]
            if mismatched:
                details = ", ".join(f"{name}={environment[name].currency}" for name in mismatched)
                raise CalcError(f"计算项 {item['id']} 存在币种不一致：{details}，目标={item['currency']}")
            result_unit = "money"
            result_currency = item["currency"]
        else:
            if money_references:
                raise CalcError(f"数量计算项 {item['id']} 不得直接引用金额：{', '.join(money_references)}")
            result_unit = item["unit"]
            result_currency = None

        quantum_text = item["rounding"]["quantum"]
        quantum = decimal_to_fraction(quantum_text)
        rounded = round_fraction(exact, quantum, item["rounding"]["mode"])
        referenced_values = {
            name: {
                "exact_fraction": fraction_text(environment[name].value),
                "unit": environment[name].unit,
                **({"currency": environment[name].currency} if environment[name].currency else {}),
            }
            for name in references
        }
        trace: dict[str, Any] = {
            "id": item["id"],
            "label": item["label"],
            "category": item["category"],
            "formula": item["formula"],
            "result_type": item["result_type"],
            "exact_fraction": fraction_text(exact),
            "unrounded_decimal_preview": decimal_preview(exact),
            "rounded_value": format_rounded(rounded, quantum_text),
            "rounding": {
                "quantum": quantum_text,
                "mode": item["rounding"]["mode"],
                "rounded_fraction": fraction_text(rounded),
            },
            "referenced_values": referenced_values,
            "source_ids": item["source_ids"],
        }
        if result_currency:
            trace["currency"] = result_currency
        else:
            trace["unit"] = result_unit
        calculation_traces.append(trace)
        environment[item["id"]] = ValueMeta(value=rounded, unit=result_unit, currency=result_currency)

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    canonical = canonical_input_bytes(data)
    return {
        "schema_version": "1.0",
        "status": "calculated_unreviewed",
        "lawyer_reviewed": False,
        "artifact_role": "sidecar_calculation_report",
        "engine_version": ENGINE_VERSION,
        "generated_at": generated_at,
        "canonical_input_sha256": hashlib.sha256(canonical).hexdigest(),
        "matter": data["matter"],
        "as_of_date": data["as_of_date"],
        "benchmarks": data["benchmarks"],
        "variables": variable_traces,
        "calculations": calculation_traces,
        "disclaimer": DISCLAIMER,
    }


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 案件确定性计算旁路报告",
        "",
        f"- 案件标识：{report['matter']['matter_id']}",
        f"- 案件名称：{report['matter']['matter_name']}",
        f"- 核验基准日：{report['as_of_date']}",
        f"- 报告状态：{report['status']}",
        f"- 律师已审查：{'yes' if report['lawyer_reviewed'] else 'no'}",
        f"- 输入 SHA-256：`{report['canonical_input_sha256']}`",
        f"- 计算引擎：`{report['engine_version']}`",
        f"- 生成时间：{report['generated_at']}",
        "",
        "## 基准来源",
        "",
        "| ID | 类型 | 标题 | 定位 | 核验日 | 适用状态 |",
        "|---|---|---|---|---|---|",
    ]
    for source in report["benchmarks"]:
        lines.append(
            "| " + " | ".join(
                _cell(source[key])
                for key in ("id", "source_type", "title", "locator", "verified_on", "applicability_status")
            ) + " |"
        )

    lines.extend(["", "### 来源原文摘录", ""])
    for source in report["benchmarks"]:
        lines.append(f"> {source['id']}：{source['quote']}")
        lines.append("")

    lines.extend([
        "## 输入变量",
        "",
        "| ID | 名称 | 类型 | 精确值 | 单位/币种 | 来源 |",
        "|---|---|---|---|---|---|",
    ])
    for variable in report["variables"]:
        unit = variable.get("currency", variable["unit"])
        lines.append(
            f"| {_cell(variable['id'])} | {_cell(variable['label'])} | {_cell(variable['kind'])} | "
            f"{_cell(variable['exact_fraction'])} | {_cell(unit)} | {_cell(', '.join(variable['source_ids']))} |"
        )
        if "period_trace" in variable:
            period = variable["period_trace"]
            lines.append(
                f"\n> {variable['id']} 期间边界：{period['start_date']} 至 {period['end_date']}；"
                f"计入起日：{'是' if period['include_start'] else '否'}；"
                f"计入止日：{'是' if period['include_end'] else '否'}；"
                f"日历日：{period['calendar_days']}。\n"
            )

    lines.extend([
        "## 计算结果",
        "",
        "| ID | 项目 | 类别 | 公式 | 精确分数 | 未舍入预览 | 舍入后 | 规则 | 来源 |",
        "|---|---|---|---|---|---|---|---|---|",
    ])
    for item in report["calculations"]:
        unit = item.get("currency", item.get("unit", ""))
        rule = f"{item['rounding']['quantum']} / {item['rounding']['mode']}"
        rounded = f"{item['rounded_value']} {unit}".strip()
        lines.append(
            f"| {_cell(item['id'])} | {_cell(item['label'])} | {_cell(item['category'])} | "
            f"`{_cell(item['formula'])}` | {_cell(item['exact_fraction'])} | "
            f"{_cell(item['unrounded_decimal_preview'])} | {_cell(rounded)} | {_cell(rule)} | "
            f"{_cell(', '.join(item['source_ids']))} |"
        )

    lines.extend([
        "",
        "## 使用边界",
        "",
        report["disclaimer"],
        "",
        "本文件仅是旁路计算工作纸，不会自动回填诉请或任何法律文书。",
        "",
    ])
    return "\n".join(lines)


def atomic_write_new(outputs: dict[Path, bytes]) -> None:
    normalized = [path.resolve(strict=False) for path in outputs]
    if len(normalized) != len(set(normalized)):
        raise CalcError("输出路径不得重复。")
    for path in outputs:
        if path.exists():
            raise CalcError(f"输出已存在，拒绝覆盖：{path}")
        if not path.parent.exists() or not path.parent.is_dir():
            raise CalcError(f"输出目录不存在：{path.parent}")

    staged: list[tuple[Path, Path]] = []
    created: list[Path] = []
    try:
        for path, content in outputs.items():
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temporary, path))
        for temporary, target in staged:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise CalcError(f"输出在写入期间已存在，拒绝覆盖：{target}") from exc
            created.append(target)
    except Exception:
        for target in created:
            try:
                target.unlink()
            except OSError:
                pass
        raise
    finally:
        for temporary, _ in staged:
            try:
                temporary.unlink()
            except OSError:
                pass


def ensure_distinct_from_input(input_path: Path, output_paths: Iterable[Path]) -> None:
    resolved_input = input_path.resolve(strict=True)
    for path in output_paths:
        if path.resolve(strict=False) == resolved_input:
            raise CalcError(f"输出路径不得与输入相同：{path}")


def serialize_report(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
