#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入根节点必须是对象")
    return value


def schema_errors(value: dict[str, Any], skill_root: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        return ["缺少 jsonschema，无法执行结构校验"]
    schema = json.loads((skill_root / "schemas" / "timeline.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"Schema {'.'.join(str(part) for part in error.path) or '<root>'}：{error.message}"
        for error in validator.iter_errors(value)
    ]


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def validate(value: dict[str, Any], skill_root: Path) -> dict[str, Any]:
    errors = schema_errors(value, skill_root)
    warnings: list[str] = []
    events = value.get("events", [])
    ids = [event.get("event_id") for event in events]
    duplicates = sorted({event_id for event_id in ids if event_id and ids.count(event_id) > 1})
    if duplicates:
        errors.append(f"事件编号重复：{'、'.join(duplicates)}")

    for event in events:
        event_id = event.get("event_id", "未知事件")
        date_value = event.get("date", {})
        precision = date_value.get("precision")
        try:
            start = parse_date(date_value.get("start"))
            end = parse_date(date_value.get("end"))
        except ValueError:
            errors.append(f"{event_id} 含无效公历日期")
            continue
        if precision == "unknown" and (start or end):
            errors.append(f"{event_id} 为 unknown，但填写了规范化日期")
        if precision != "unknown" and (not start or not end):
            errors.append(f"{event_id} 的 {precision} 日期必须同时填写 start 和 end")
        if start and end and start > end:
            errors.append(f"{event_id} 的起始日期晚于结束日期")
        if precision == "exact" and start != end:
            errors.append(f"{event_id} 的 exact 日期必须为同一天")
        if event.get("status") == "user_confirmed" and not event.get("source_spans") and not event.get("confirmation_note"):
            errors.append(f"{event_id} 已确认但没有来源或确认说明")
        if event.get("status") == "derived" and not event.get("derivation_rule"):
            errors.append(f"{event_id} 为 derived 但没有推导规则")
        if not event.get("source_spans"):
            warnings.append(f"{event_id} 没有材料来源定位")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def interval(event: dict[str, Any]) -> tuple[date, date] | None:
    value = event["date"]
    if value["precision"] == "unknown":
        return None
    return date.fromisoformat(value["start"]), date.fromisoformat(value["end"])


def build_result(value: dict[str, Any]) -> dict[str, Any]:
    events = list(value["events"])
    events.sort(key=lambda event: (interval(event) is None, interval(event) or (date.max, date.max), event["event_id"]))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        key = event.get("comparison_key")
        if key:
            grouped.setdefault(key, []).append(event)
    conflicts: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        dated = [(item, interval(item)) for item in items if interval(item)]
        incompatible: set[str] = set()
        for index, (left, left_interval) in enumerate(dated):
            assert left_interval is not None
            for right, right_interval in dated[index + 1:]:
                assert right_interval is not None
                if left_interval[1] < right_interval[0] or right_interval[1] < left_interval[0]:
                    incompatible.update((left["event_id"], right["event_id"]))
        if incompatible:
            conflicts.append({"comparison_key": key, "event_ids": sorted(incompatible), "reason": "同一事件的日期区间互不重叠"})
    unresolved = [
        event["event_id"]
        for event in events
        if event["date"]["precision"] == "unknown" or event["status"] in {"missing", "conflict", "unreadable"}
    ]
    trigger_candidates = [event["event_id"] for event in events if event["deadline_trigger_candidate"]]
    return {
        "schema_version": "1.0",
        "timeline_id": value["timeline_id"],
        "matter_id": value["matter_id"],
        "cutoff_date": value["cutoff_date"],
        "events": events,
        "date_conflicts": conflicts,
        "unresolved_event_ids": unresolved,
        "deadline_trigger_candidate_ids": trigger_candidates,
        "artifact_state": "lawyer_review_required",
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 案件时间轴",
        "",
        f"案件编号：{result['matter_id']}  ",
        f"时间轴编号：{result['timeline_id']}  ",
        f"材料截止日期：{result['cutoff_date']}",
        "",
        "## 一、按日期排列的事件",
        "",
    ]
    for event in result["events"]:
        date_value = event["date"]
        normalized = "日期待确认" if date_value["precision"] == "unknown" else f"{date_value['start']}至{date_value['end']}"
        trigger = "｜期限触发候选" if event["deadline_trigger_candidate"] else ""
        lines.append(f"- {normalized}｜{event['event_id']}｜{event['description']}｜{event['status']}{trigger}")
    lines.extend(["", "## 二、日期冲突", ""])
    if result["date_conflicts"]:
        for item in result["date_conflicts"]:
            lines.append(f"- {item['comparison_key']}：{'、'.join(item['event_ids'])}——{item['reason']}")
    else:
        lines.append("- 未发现机器可识别的非重叠日期冲突。")
    lines.extend(["", "## 三、待核验与期限衔接", ""])
    lines.append(f"- 待核验事件：{'、'.join(result['unresolved_event_ids']) or '无'}")
    lines.append(f"- 期限触发候选：{'、'.join(result['deadline_trigger_candidate_ids']) or '无'}")
    lines.append("- 期限触发候选不等于法定起算点，必须交由期限计算流程和律师核验。")
    return "\n".join(lines) + "\n"


def build(input_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    value = load_json(input_path)
    skill_root = Path(__file__).resolve().parent.parent
    validation = validate(value, skill_root)
    if not validation["ok"]:
        raise ValueError("；".join(validation["errors"]))
    result = build_result(value)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-timeline-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        (temp / "timeline.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "案件时间轴.md").write_text(markdown(result), encoding="utf-8")
        temp.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="建立可回查的中国法律案件事实与程序时间轴")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.input, args.output)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] 已生成案件时间轴：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

