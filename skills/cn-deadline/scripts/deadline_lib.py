#!/usr/bin/env python3
"""期限输入校验与确定性计算共享库。"""

from __future__ import annotations

import calendar as month_calendar
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator, FormatChecker


MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_ITERATION_DAYS = 500_000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OFFSET_RE = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")


class InputError(ValueError):
    """输入结构、编码或交叉字段错误。"""


class CalculationBlocked(RuntimeError):
    """计算条件不完整，不应猜测结果。"""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"存在重复 JSON 键：{key}")
        result[key] = value
    return result


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise InputError("拒绝读取符号链接输入。")
    if not path.is_file():
        raise InputError(f"输入文件不存在：{path}")
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise InputError(f"输入超过 {MAX_INPUT_BYTES} 字节限制。")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError("输入必须是 UTF-8 编码。") from exc
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, InputError) as exc:
        raise InputError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise InputError("JSON 顶层必须是对象。")
    return data, raw


def _schema_path(filename: str) -> Path:
    return Path(__file__).resolve().parent.parent / "schemas" / filename


def load_schema(filename: str) -> dict[str, Any]:
    with _schema_path(filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _format_json_path(parts: Any) -> str:
    result = "$"
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def validate_schema(instance: dict[str, Any], filename: str) -> None:
    validator = Draft202012Validator(load_schema(filename), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    if errors:
        messages = [f"{_format_json_path(error.absolute_path)}: {error.message}" for error in errors]
        raise InputError("模式校验失败：\n- " + "\n- ".join(messages))


def parse_date(value: str) -> date:
    if not DATE_RE.fullmatch(value):
        raise InputError(f"日期必须为 YYYY-MM-DD：{value}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"无效日期：{value}") from exc


def parse_zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InputError(f"无效 IANA 时区：{value}") from exc


def validate_input(data: dict[str, Any]) -> None:
    validate_schema(data, "deadline-input.schema.json")
    as_of = parse_date(data["as_of_date"])
    calendar_ids: set[str] = set()
    calendars: dict[str, dict[str, Any]] = {}
    source_registry: dict[str, str] = {}

    def register_source(source: dict[str, Any], location: str) -> None:
        canonical = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        previous = source_registry.get(source["source_id"])
        if previous is not None and previous != canonical:
            raise InputError(f"来源 ID {source['source_id']} 对应了不同内容：{location}")
        source_registry[source["source_id"]] = canonical
        parse_date(source["verified_on"])

    for index, item in enumerate(data["calendars"]):
        calendar_id = item["calendar_id"]
        if calendar_id in calendar_ids:
            raise InputError(f"重复日历 ID：{calendar_id}")
        calendar_ids.add(calendar_id)
        calendars[calendar_id] = item
        parse_zone(item["timezone"])
        start = parse_date(item["coverage_start"])
        end = parse_date(item["coverage_end"])
        if start > end:
            raise InputError(f"日历 {calendar_id} 覆盖起日晚于止日。")
        non_working = set(item["non_working_dates"])
        working = set(item["working_dates"])
        overlap = sorted(non_working & working)
        if overlap:
            raise InputError(f"日历 {calendar_id} 工作日与非工作日重叠：{', '.join(overlap)}")
        for value in non_working | working:
            current = parse_date(value)
            if current < start or current > end:
                raise InputError(f"日历 {calendar_id} 的例外日期超出覆盖范围：{value}")
        register_source(item["source"], f"calendars[{index}].source")

    deadline_ids: set[str] = set()
    for d_index, item in enumerate(data["deadlines"]):
        deadline_id = item["deadline_id"]
        if deadline_id in deadline_ids:
            raise InputError(f"重复期限 ID：{deadline_id}")
        deadline_ids.add(deadline_id)
        parse_zone(item["timezone"])
        parse_date(item["event"]["operative_date"])
        occurred = item["event"].get("occurred_at")
        if occurred:
            if not OFFSET_RE.search(occurred):
                raise InputError(f"期限 {deadline_id} 的 occurred_at 必须带 UTC 偏移。")
            try:
                datetime.fromisoformat(occurred.replace("Z", "+00:00"))
            except ValueError as exc:
                raise InputError(f"期限 {deadline_id} 的 occurred_at 无效。") from exc
        rule = item["rule"]
        register_source(rule["source"], f"deadlines[{d_index}].rule.source")
        required_calendar = rule.get("calendar_id")
        if required_calendar and required_calendar not in calendars:
            raise InputError(f"期限 {deadline_id} 引用未定义日历：{required_calendar}")
        adjustment_ids: set[str] = set()
        for a_index, adjustment in enumerate(item["adjustments"]):
            adjustment_id = adjustment["adjustment_id"]
            if adjustment_id in adjustment_ids:
                raise InputError(f"期限 {deadline_id} 存在重复调整 ID：{adjustment_id}")
            adjustment_ids.add(adjustment_id)
            register_source(adjustment["source"], f"deadlines[{d_index}].adjustments[{a_index}].source")
            calendar_id = adjustment.get("calendar_id")
            if calendar_id and calendar_id not in calendars:
                raise InputError(f"调整 {adjustment_id} 引用未定义日历：{calendar_id}")
        if as_of < date(1900, 1, 1):
            raise InputError("as_of_date 早于可支持范围。")


@dataclass(frozen=True)
class WorkCalendar:
    item: dict[str, Any]

    @property
    def calendar_id(self) -> str:
        return self.item["calendar_id"]

    def is_working(self, current: date) -> bool:
        start = parse_date(self.item["coverage_start"])
        end = parse_date(self.item["coverage_end"])
        if not self.item["declared_complete"]:
            raise CalculationBlocked(f"日历 {self.calendar_id} 未声明为完整日历。")
        if current < start or current > end:
            raise CalculationBlocked(f"日期 {current.isoformat()} 超出日历 {self.calendar_id} 覆盖范围。")
        value = current.isoformat()
        if value in self.item["non_working_dates"]:
            return False
        if value in self.item["working_dates"]:
            return True
        return current.weekday() not in self.item["weekend_weekdays"]


def _source_blockers(source: dict[str, Any], as_of: date, label: str) -> list[str]:
    blockers: list[str] = []
    if source["effect_status"] != "effective":
        blockers.append(f"{label}来源 {source['source_id']} 效力状态为 {source['effect_status']}。")
    verified = parse_date(source["verified_on"])
    if verified > as_of:
        blockers.append(f"{label}来源 {source['source_id']} 核验日晚于计算基准日。")
    return blockers


def _calendar_for(
    calendars: dict[str, WorkCalendar], calendar_id: str | None, timezone: str, as_of: date
) -> tuple[WorkCalendar | None, list[str]]:
    if not calendar_id:
        return None, ["计算需要工作日日历，但未指定 calendar_id。"]
    calendar = calendars.get(calendar_id)
    if calendar is None:
        return None, [f"未找到日历 {calendar_id}。"]
    blockers: list[str] = []
    if calendar.item["timezone"] != timezone:
        blockers.append(f"日历 {calendar_id} 时区与期限时区不一致。")
    if not calendar.item["declared_complete"]:
        blockers.append(f"日历 {calendar_id} 未声明为完整日历。")
    blockers.extend(_source_blockers(calendar.item["source"], as_of, "日历"))
    return calendar, blockers


def _count_days(start: date, count: int, include_start: bool, day_kind: str, work_calendar: WorkCalendar | None) -> date:
    if day_kind == "calendar":
        return start + timedelta(days=count - 1 if include_start else count)
    if work_calendar is None:
        raise CalculationBlocked("缺少工作日日历。")
    current = start if include_start else start + timedelta(days=1)
    accepted = 0
    iterations = 0
    while accepted < count:
        iterations += 1
        if iterations > MAX_ITERATION_DAYS:
            raise CalculationBlocked("工作日计算超过安全迭代上限。")
        if work_calendar.is_working(current):
            accepted += 1
            if accepted == count:
                return current
        current += timedelta(days=1)
    raise AssertionError("不可到达")


def _add_anniversary(start: date, unit: str, count: int, invalid_day_policy: str) -> date:
    months = count if unit == "months" else count * 12
    absolute_month = start.year * 12 + (start.month - 1) + months
    year, month_index = divmod(absolute_month, 12)
    month = month_index + 1
    last_day = month_calendar.monthrange(year, month)[1]
    if start.day > last_day:
        if invalid_day_policy == "block":
            raise CalculationBlocked(f"目标月 {year:04d}-{month:02d} 不存在 {start.day} 日，规则要求阻断。")
        return date(year, month, last_day)
    return date(year, month, start.day)


def _shift_to_working(current: date, direction: int, work_calendar: WorkCalendar) -> date:
    iterations = 0
    while not work_calendar.is_working(current):
        iterations += 1
        if iterations > MAX_ITERATION_DAYS:
            raise CalculationBlocked("到期日调整超过安全迭代上限。")
        current += timedelta(days=direction)
    return current


def _make_step(sequence: int, operation: str, detail: str, source_id: str, before: date | None, after: date | None) -> dict[str, Any]:
    step: dict[str, Any] = {
        "sequence": sequence,
        "operation": operation,
        "detail": detail,
        "source_id": source_id,
    }
    if before is not None:
        step["input_date"] = before.isoformat()
    if after is not None:
        step["output_date"] = after.isoformat()
    return step


def calculate(data: dict[str, Any], raw: bytes) -> dict[str, Any]:
    validate_input(data)
    as_of = parse_date(data["as_of_date"])
    calendars = {item["calendar_id"]: WorkCalendar(item) for item in data["calendars"]}
    results: list[dict[str, Any]] = []

    for item in data["deadlines"]:
        rule = item["rule"]
        source = rule["source"]
        event = item["event"]
        operative = parse_date(event["operative_date"])
        blockers = list(item["blocking_questions"])
        warnings: list[str] = []
        steps: list[dict[str, Any]] = []

        if not event["confirmed_by_human"]:
            blockers.append("操作性起算日未经人工确认。")
        blockers.extend(_source_blockers(source, as_of, "期限规则"))
        if operative > as_of:
            warnings.append("操作性起算日晚于计算基准日，请复核是否为预计事件。")
        if event.get("occurred_at"):
            occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
            local_date = occurred.astimezone(parse_zone(item["timezone"])).date()
            if local_date != operative:
                warnings.append("证据时间折算的本地日期与操作性起算日不同，已按人工确认的起算日计算。")

        calculation = rule["calculation"]
        needed_calendar_ids: set[str] = set()
        if calculation["method"] == "counted_days" and calculation["day_kind"] == "working":
            needed_calendar_ids.add(rule.get("calendar_id", ""))
        if rule["non_working_expiry"] != "keep":
            needed_calendar_ids.add(rule.get("calendar_id", ""))
        for adjustment in item["adjustments"]:
            blockers.extend(_source_blockers(adjustment["source"], as_of, f"调整 {adjustment['adjustment_id']}"))
            if adjustment["type"] == "add_days" and adjustment["day_kind"] == "working":
                needed_calendar_ids.add(adjustment.get("calendar_id", ""))
        for calendar_id in sorted(needed_calendar_ids):
            _, calendar_blockers = _calendar_for(calendars, calendar_id or None, item["timezone"], as_of)
            blockers.extend(calendar_blockers)

        result: dict[str, Any] = {
            "deadline_id": item["deadline_id"],
            "label": item["label"],
            "status": "blocked" if blockers else "calculated",
            "timezone": item["timezone"],
            "operative_date": operative.isoformat(),
            "rule_id": rule["rule_id"],
            "rule_source_id": source["source_id"],
            "deadline_time": rule["deadline_time"],
            "steps": steps,
            "exceptions": list(item["exceptions"]),
            "warnings": warnings,
            "blockers": blockers,
        }

        if not blockers:
            try:
                current: date
                if calculation["method"] == "counted_days":
                    work_calendar = None
                    if calculation["day_kind"] == "working":
                        work_calendar = calendars[rule["calendar_id"]]
                    current = _count_days(
                        operative,
                        calculation["count"],
                        calculation["include_operative_date"],
                        calculation["day_kind"],
                        work_calendar,
                    )
                    detail = (
                        f"按{'工作日' if calculation['day_kind'] == 'working' else '日历日'}"
                        f"计数 {calculation['count']} 日，"
                        f"{'计入' if calculation['include_operative_date'] else '不计入'}操作性起算日。"
                    )
                    steps.append(_make_step(1, "counted_days", detail, source["source_id"], operative, current))
                else:
                    current = _add_anniversary(
                        operative,
                        calculation["unit"],
                        calculation["count"],
                        calculation["invalid_day_policy"],
                    )
                    detail = (
                        f"按周年日法增加 {calculation['count']} "
                        f"{'个月' if calculation['unit'] == 'months' else '年'}；"
                        f"无对应日时策略为 {calculation['invalid_day_policy']}。"
                    )
                    steps.append(_make_step(1, "anniversary", detail, source["source_id"], operative, current))

                for adjustment in item["adjustments"]:
                    before = current
                    if adjustment["type"] == "set_date":
                        current = parse_date(adjustment["date"])
                        detail = f"根据显式调整指定日期：{adjustment['reason']}"
                    else:
                        work_calendar = None
                        if adjustment["day_kind"] == "working":
                            work_calendar = calendars[adjustment["calendar_id"]]
                        current = _count_days(
                            before,
                            adjustment["count"],
                            adjustment["include_current_date"],
                            adjustment["day_kind"],
                            work_calendar,
                        )
                        detail = (
                            f"根据显式调整增加 {adjustment['count']} "
                            f"{'工作日' if adjustment['day_kind'] == 'working' else '日历日'}："
                            f"{adjustment['reason']}"
                        )
                    steps.append(
                        _make_step(
                            len(steps) + 1,
                            adjustment["type"],
                            detail,
                            adjustment["source"]["source_id"],
                            before,
                            current,
                        )
                    )

                if rule["non_working_expiry"] != "keep":
                    before = current
                    work_calendar = calendars[rule["calendar_id"]]
                    direction = 1 if rule["non_working_expiry"] == "next_working_day" else -1
                    current = _shift_to_working(current, direction, work_calendar)
                    steps.append(
                        _make_step(
                            len(steps) + 1,
                            rule["non_working_expiry"],
                            f"按规则将到期日调整为工作日，日历为 {work_calendar.calendar_id}。",
                            source["source_id"],
                            before,
                            current,
                        )
                    )

                zone = parse_zone(item["timezone"])
                hours, minutes, seconds = (int(part) for part in rule["deadline_time"].split(":"))
                deadline_at = datetime(current.year, current.month, current.day, hours, minutes, seconds, tzinfo=zone)
                result["deadline_date"] = current.isoformat()
                result["deadline_at"] = deadline_at.isoformat()
                if current < as_of:
                    result["warnings"].append("按输入规则计算的截止日早于计算基准日。")
            except CalculationBlocked as exc:
                result["status"] = "blocked"
                result["steps"] = []
                result["blockers"].append(str(exc))
                result.pop("deadline_date", None)
                result.pop("deadline_at", None)

        results.append(result)

    output = {
        "schema_version": "1.0",
        "matter_id": data["matter_id"],
        "as_of_date": data["as_of_date"],
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "results": results,
    }
    validate_schema(output, "deadline-output.schema.json")
    return output
