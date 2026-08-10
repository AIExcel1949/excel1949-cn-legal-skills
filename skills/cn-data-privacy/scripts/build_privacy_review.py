#!/usr/bin/env python3
"""确定性生成个人信息保护审查 JSON 与 Markdown，不执行系统操作或通知。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = SKILL_DIR / "schemas" / "privacy-input.schema.json"
OUTPUT_SCHEMA = SKILL_DIR / "schemas" / "privacy-output.schema.json"
AUTHORITY_REGISTRY = SKILL_DIR / "references" / "official-sources.json"
AUTHOR = "AIOffice职场通关-excel1949"
ACTION_CONTROLS = {
    "auto_delete": False,
    "auto_notify_regulator": False,
    "auto_notify_individual": False,
    "auto_submit": False,
    "auto_transfer_cross_border": False,
    "auto_change_system": False,
}


class InputError(ValueError):
    """输入、引用、哈希或安全门禁错误。"""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"重复 JSON 键：{key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"无效 UTF-8 JSON：{exc}") from exc


def _schema(path: Path) -> dict[str, Any]:
    return _load_json(path)


def _unique_ids(items: Iterable[dict[str, Any]], key: str, label: str) -> set[str]:
    values = [item[key] for item in items]
    if len(values) != len(set(values)):
        raise InputError(f"{label}中 {key} 不得重复")
    return set(values)


def _require_refs(values: Iterable[str], allowed: set[str], label: str) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise InputError(f"{label}引用未定义编号：{'\u3001'.join(unknown)}")


def authority_registry() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    registry = _load_json(AUTHORITY_REGISTRY)
    records = registry["sources"]
    ids = _unique_ids(records, "authority_id", "官方法源登记表")
    if not ids:
        raise InputError("官方法源登记表为空")
    return {item["authority_id"]: item for item in records}, registry


def validate_semantics(data: dict[str, Any]) -> None:
    source_ids = _unique_ids(data["sources"], "source_id", "原始来源")
    for source in data["sources"]:
        actual = hashlib.sha256(source["original_text"].encode("utf-8")).hexdigest()
        if actual != source["sha256"]:
            raise InputError(f"原文 SHA-256 不匹配：{source['source_id']}")
        if source["verification_status"] == "unverified" and source["verified_on"] is not None:
            raise InputError(f"未核验来源不得填写核验日期：{source['source_id']}")
        if source["verification_status"] != "unverified" and source["verified_on"] is None:
            raise InputError(f"已核验来源必须填写核验日期：{source['source_id']}")

    authority_map, _ = authority_registry()
    _require_refs(data["authority_ids"], set(authority_map), "法源")
    data_item_ids = _unique_ids(data["data_inventory"], "data_item_id", "数据盘点")
    for item in data["data_inventory"]:
        _require_refs(item["source_ids"], source_ids, f"数据项 {item['data_item_id']}")

    activity_ids = _unique_ids(data["processing_activities"], "activity_id", "处理活动")
    recipient_ids: list[str] = []
    for activity in data["processing_activities"]:
        _require_refs(activity["data_item_ids"], data_item_ids, f"处理活动 {activity['activity_id']} 数据项")
        for recipient in activity["recipients"]:
            recipient_ids.append(recipient["recipient_id"])
            _require_refs(recipient["source_ids"], source_ids, f"接收方 {recipient['recipient_id']}")
        cross = activity["cross_border"]
        if cross["involved"] and "not_applicable" in cross["mechanism_candidates"]:
            raise InputError(f"活动 {activity['activity_id']} 已涉及出境，不得使用 not_applicable 路径")
        if not cross["involved"] and cross["mechanism_candidates"] != ["not_applicable"]:
            raise InputError(f"活动 {activity['activity_id']} 不涉及出境时路径候选必须仅为 not_applicable")
    if len(recipient_ids) != len(set(recipient_ids)):
        raise InputError("recipient_id 不得重复")

    _unique_ids(data["pia_records"], "pia_id", "个人信息保护影响评估")
    for pia in data["pia_records"]:
        _require_refs(pia["activity_ids"], activity_ids, f"影响评估 {pia['pia_id']}")

    _unique_ids(data["incidents"], "incident_id", "安全事件")
    task_ids: list[str] = []
    for incident in data["incidents"]:
        _require_refs(incident["source_ids"], source_ids, f"事件 {incident['incident_id']}")
        task_ids.extend(task["task_id"] for task in incident["response_tasks"])
    if len(task_ids) != len(set(task_ids)):
        raise InputError("task_id 不得重复")

    _unique_ids(data["individual_requests"], "request_id", "个人权利请求")
    for request in data["individual_requests"]:
        _require_refs(request["source_ids"], source_ids, f"请求 {request['request_id']}")


def load_input(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"无效 UTF-8 JSON：{exc}") from exc
    errors = sorted(
        Draft202012Validator(_schema(INPUT_SCHEMA), format_checker=FormatChecker()).iter_errors(data),
        key=lambda item: [str(part) for part in item.absolute_path],
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise InputError(f"Schema 校验失败 {location}：{first.message}")
    validate_semantics(data)
    return data, raw


def _activity_requires_pia(activity: dict[str, Any]) -> bool:
    return (
        activity["sensitive_context"]["candidate_present"]
        or activity["minor_context"]["candidate_present"]
        or activity["cross_border"]["involved"]
        or activity["high_impact_candidate"]
        or bool(activity["recipients"])
    )


def build_review(data: dict[str, Any], raw: bytes) -> dict[str, Any]:
    authority_map, registry = authority_registry()
    selected_set = set(data["authority_ids"])
    selected = [item for item in registry["sources"] if item["authority_id"] in selected_set]
    inventory = [
        {
            **item,
            "classification_state": "candidate_only_no_determination",
            "automatic_deletion_permitted": False,
        }
        for item in data["data_inventory"]
    ]
    processing = []
    blockers: list[str] = []
    for activity in data["processing_activities"]:
        processing.append({
            **activity,
            "legal_basis_state": "candidate_only_no_selection",
            "recipient_relationship_state": "candidate_only_no_determination",
            "cross_border_mechanism_state": "candidate_only_no_selection",
            "legality_conclusion": "not_determined",
        })
        if activity["notice_status"] in {"missing", "unknown", "partial"}:
            blockers.append(f"告知记录待复核：{activity['activity_id']}")
        if activity["consent_status"] in {"missing", "unknown", "partial"}:
            blockers.append(f"同意或其他基础记录待复核：{activity['activity_id']}")
        sensitive = activity["sensitive_context"]
        if sensitive["candidate_present"] and (
            not sensitive["specific_purpose"]
            or not sensitive["necessity_note"]
            or sensitive["separate_consent_status"] in {"missing", "unknown", "partial"}
        ):
            blockers.append(f"敏感个人信息特别要求待复核：{activity['activity_id']}")
        minor = activity["minor_context"]
        if minor["candidate_present"] and minor["guardian_consent_status"] in {"missing", "unknown", "partial"}:
            blockers.append(f"未成年人与监护人同意记录待复核：{activity['activity_id']}")
        for recipient in activity["recipients"]:
            if recipient["relationship_candidate"] == "unknown" or recipient["contract_status"] != "documented":
                blockers.append(f"接收方关系或合同待复核：{recipient['recipient_id']}")
        cross = activity["cross_border"]
        if cross["involved"] and "unknown" in cross["mechanism_candidates"]:
            blockers.append(f"数据出境路径待研究：{activity['activity_id']}")

    for item in data["data_inventory"]:
        if "unknown" in item["classification_candidates"]:
            blockers.append(f"数据分类待确认：{item['data_item_id']}")
        if item["deletion_state"] in {"task_candidate", "unknown"}:
            blockers.append(f"保存与删除任务待人工复核：{item['data_item_id']}")

    covered = {activity_id for pia in data["pia_records"] for activity_id in pia["activity_ids"]}
    pia_required = {
        activity["activity_id"]
        for activity in data["processing_activities"]
        if _activity_requires_pia(activity)
    }
    pia_gaps = sorted(pia_required - covered)
    blockers.extend(f"个人信息保护影响评估覆盖缺口：{activity_id}" for activity_id in pia_gaps)

    incident_queue = []
    for incident in data["incidents"]:
        for task in incident["response_tasks"]:
            incident_queue.append({
                "incident_id": incident["incident_id"],
                "severity_candidate": incident["severity_candidate"],
                **task,
                "execution_permitted": False,
                "notification_permitted": False,
            })
            if task["action_type"] in {"assess_notification", "draft_notification"}:
                blockers.append(f"事件通知义务与通道待人工判断：{task['task_id']}")

    request_queue = [
        {
            **request,
            "execution_permitted": False,
            "lawyer_review_required": True,
        }
        for request in data["individual_requests"]
    ]
    blockers.extend(
        f"个人权利请求待人工处理：{request['request_id']}"
        for request in request_queue
    )
    blockers.extend(
        f"原始来源尚未核验：{source['source_id']}"
        for source in data["sources"]
        if source["verification_status"] == "unverified"
    )

    result = {
        "schema_version": "1.0",
        "author": AUTHOR,
        "artifact_state": "lawyer_review_required",
        "matter": data["matter"],
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "sources": data["sources"],
        "selected_authorities": selected,
        "inventory_matrix": inventory,
        "processing_matrix": processing,
        "pia_matrix": [
            {**pia, "assessment_state": "lawyer_review_required", "automatic_approval": False}
            for pia in data["pia_records"]
        ],
        "pia_gaps": pia_gaps,
        "incident_task_queue": incident_queue,
        "individual_request_queue": request_queue,
        "blockers": blockers,
        "action_controls": dict(ACTION_CONTROLS),
    }
    Draft202012Validator(_schema(OUTPUT_SCHEMA), format_checker=FormatChecker()).validate(result)
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 个人信息保护审查工作簿",
        "",
        f"-作者：{result['author']}",
        f"-事项：{result['matter']['title']}",
        f"-基准日：{result['matter']['as_of_date']}",
        "-文件状态：待执业律师复核",
        "-禁止操作：不得自动删除、通知、提交、出境传输或变更系统",
        "",
        "## 数据盘点（分类仅为候选）",
        "",
        "|数据项|分类候选|系统|删除状态|",
        "|---|---|---|---|",
    ]
    for item in result["inventory_matrix"]:
        lines.append(f"|{item['label']}|{'\u3001'.join(item['classification_candidates'])}|{'\u3001'.join(item['systems'])}|{item['deletion_state']}|")
    lines.extend(["", "## 处理活动", ""])
    for activity in result["processing_matrix"]:
        lines.extend([
            f"### {activity['activity_id']}·{activity['name']}",
            "",
            f"-目的：{activity['purpose']}",
            f"-合法性基础候选：{'\u3001'.join(activity['legal_basis_candidates'])}",
            f"-出境路径候选：{'\u3001'.join(activity['cross_border']['mechanism_candidates'])}",
            "-合法性结论：未作认定，待执业律师复核",
            "",
        ])
    lines.extend(["## 影响评估缺口", ""])
    lines.extend([f"- {item}" for item in result["pia_gaps"]] or ["- 未发现结构性覆盖缺口，仍需复核评估质量。"])
    lines.extend(["", "## 原始来源", ""])
    for source in result["sources"]:
        lines.append(f"- {source['source_id']}：{source['source_locator']}；SHA-256 `{source['sha256']}`；{source['verification_status']}")
    lines.extend(["", "## 事件响应任务（不得自动通知）", ""])
    lines.extend([f"- {item['task_id']}：{item['description']}；仅限人工执行" for item in result["incident_task_queue"]] or ["- 无已录入事件任务。"])
    lines.extend(["", "## 个人权利请求（不得自动删除或操作）", ""])
    lines.extend([f"- {item['request_id']}：{item['request_type']}；{item['task_description']}" for item in result["individual_request_queue"]] or ["- 无已录入请求。"])
    lines.extend(["", "## 阻断与待办", ""])
    lines.extend([f"- {item}" for item in result["blockers"]] or ["- 无程序性阻断，仍需律师逐项复核。"])
    return "\n".join(lines) + "\n"


def encode_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _normalized(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def write_pair_atomic(json_path: Path, json_bytes: bytes, md_path: Path, md_bytes: bytes) -> None:
    if _normalized(json_path) == _normalized(md_path):
        raise InputError("JSON 与 Markdown 输出路径不得相同")
    paths = (json_path, md_path)
    for path in paths:
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"输出已存在，拒绝覆盖：{path}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"输出目录不存在：{path.parent}")
    temps: list[Path] = []
    linked: list[Path] = []
    try:
        for target, payload in ((json_path, json_bytes), (md_path, md_bytes)):
            descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temp = Path(name)
            temps.append(temp)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        for temp, target in zip(temps, paths, strict=True):
            os.link(temp, target)
            linked.append(target)
    except Exception:
        for path in linked:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temps:
            path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成个人信息保护审查工作簿。")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if _normalized(args.input) in {_normalized(args.json_output), _normalized(args.markdown_output)}:
            raise InputError("输入与输出路径不得相同")
        data, raw = load_input(args.input)
        result = build_review(data, raw)
        write_pair_atomic(args.json_output, encode_json(result), args.markdown_output, render_markdown(result).encode("utf-8"))
    except (InputError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "artifact_state": "lawyer_review_required", "json_output": str(args.json_output), "markdown_output": str(args.markdown_output), "blocker_count": len(result["blockers"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
