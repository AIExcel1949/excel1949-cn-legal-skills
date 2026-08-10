#!/usr/bin/env python3
"""确定性生成劳动用工审查 JSON 与 Markdown，不作人事决定。"""

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
INPUT_SCHEMA = SKILL_DIR / "schemas" / "employment-input.schema.json"
OUTPUT_SCHEMA = SKILL_DIR / "schemas" / "employment-output.schema.json"
AUTHORITY_REGISTRY = SKILL_DIR / "references" / "official-sources.json"
AUTHOR = "AIOffice职场通关-excel1949"
CATEGORIES = (
    "recruitment_onboarding",
    "labor_contract",
    "work_rules",
    "pay_hours_leave",
    "social_insurance_benefits",
    "change_termination",
    "exit_handover",
    "labor_dispute",
)
ACTION_CONTROLS = {
    "auto_decide": False,
    "auto_notify": False,
    "auto_terminate": False,
    "auto_submit": False,
    "auto_sign": False,
    "auto_stamp": False,
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


def _load_json(path: Path, duplicate_guard: bool = False) -> Any:
    try:
        kwargs = {"object_pairs_hook": _pairs_no_duplicates} if duplicate_guard else {}
        return json.loads(path.read_text(encoding="utf-8"), **kwargs)
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

    candidates = set(data["relationship_review"]["candidate_types"])
    _unique_ids(data["relationship_review"]["signals"], "signal_id", "关系识别信号")
    for signal in data["relationship_review"]["signals"]:
        _require_refs(signal["source_ids"], source_ids, f"信号 {signal['signal_id']}")
        _require_refs(signal["supports_candidate_types"], candidates, f"信号 {signal['signal_id']} 候选")

    authority_map, _ = authority_registry()
    review_ids = _unique_ids(data["lifecycle_reviews"], "review_id", "全周期审查")
    if not review_ids:
        raise InputError("全周期审查不得为空")
    for review in data["lifecycle_reviews"]:
        _require_refs(review["fact_source_ids"], source_ids, f"审查 {review['review_id']} 事实")
        _require_refs(review["authority_ids"], set(authority_map), f"审查 {review['review_id']} 法源")

    _unique_ids(data["proposed_actions"], "action_id", "拟议行动")
    for action in data["proposed_actions"]:
        _require_refs(action["source_ids"], source_ids, f"行动 {action['action_id']}")
    _require_refs(data["dispute"]["source_ids"], source_ids, "劳动争议")
    if data["dispute"]["exists"] and data["dispute"]["phase_candidate"] == "none":
        raise InputError("已存在争议时阶段候选不得为 none")


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


def build_review(data: dict[str, Any], raw: bytes) -> dict[str, Any]:
    authority_map, registry = authority_registry()
    relationship = data["relationship_review"]
    candidate_matrix = []
    for candidate in relationship["candidate_types"]:
        support_ids = [
            signal["signal_id"]
            for signal in relationship["signals"]
            if candidate in signal["supports_candidate_types"]
        ]
        candidate_matrix.append({
            "candidate_type": candidate,
            "support_signal_ids": support_ids,
            "support_count": len(support_ids),
            "status": "candidate_only_no_determination",
        })

    selected_ids = []
    lifecycle = []
    for review in data["lifecycle_reviews"]:
        selected_ids.extend(review["authority_ids"])
        lifecycle.append({
            **review,
            "legal_characterization": "not_determined",
            "lawyer_conclusion_required": True,
        })
    selected_set = set(selected_ids)
    selected = [record for record in registry["sources"] if record["authority_id"] in selected_set]
    covered = {item["category"] for item in data["lifecycle_reviews"]}
    gaps = [category for category in CATEGORIES if category not in covered]

    queue = []
    for action in data["proposed_actions"]:
        if action["adverse_effect_candidate"] or action["action_type"] in {
            "reject_candidate", "change_terms", "discipline", "adjust_pay", "change_role", "terminate", "issue_notice"
        }:
            queue.append({
                **action,
                "decision_state": "human_decision_required",
                "execution_permitted": False,
            })

    blockers = [f"缺少用工阶段审查：{category}" for category in gaps]
    blockers.extend(
        f"原始来源尚未核验：{source['source_id']}"
        for source in data["sources"]
        if source["verification_status"] == "unverified"
    )
    blockers.extend(f"不利人事行动待人工决策：{item['action_id']}" for item in queue)
    blockers.extend(
        f"审查事项尚有开放问题：{review['review_id']}"
        for review in data["lifecycle_reviews"]
        if review["open_questions"]
    )
    if data["dispute"]["exists"]:
        blockers.append("已存在劳动争议，程序、时效、请求与证据需单独复核")

    result = {
        "schema_version": "1.0",
        "author": AUTHOR,
        "artifact_state": "lawyer_review_required",
        "matter": data["matter"],
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "sources": data["sources"],
        "selected_authorities": selected,
        "relationship_candidate_matrix": candidate_matrix,
        "lifecycle_matrix": lifecycle,
        "coverage_gaps": gaps,
        "human_decision_queue": queue,
        "dispute_review": {
            **data["dispute"],
            "outcome_prediction": "not_performed",
            "final_legal_conclusion": "lawyer_required",
        },
        "blockers": blockers,
        "action_controls": dict(ACTION_CONTROLS),
    }
    Draft202012Validator(_schema(OUTPUT_SCHEMA), format_checker=FormatChecker()).validate(result)
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 劳动用工全周期审查工作簿",
        "",
        f"-作者：{result['author']}",
        f"-事项：{result['matter']['title']}",
        f"-用工地：{result['matter']['employment_location']}",
        "-文件状态：待执业律师复核",
        "-禁止操作：不得自动决定、通知、解除、提交、签署或盖章",
        "",
        "## 劳动关系候选（不作定性）",
        "",
        "|候选|支持信号数|状态|",
        "|---|---:|---|",
    ]
    for item in result["relationship_candidate_matrix"]:
        lines.append(f"|{item['candidate_type']}|{item['support_count']}|仅为候选，待律师判断|")
    lines.extend(["", "## 用工周期审查", ""])
    for item in result["lifecycle_matrix"]:
        lines.extend([
            f"### {item['review_id']}·{item['category']}",
            "",
            f"-审查问题：{item['question']}",
            f"-事实来源：{'\u3001'.join(item['fact_source_ids']) or '未提供'}",
            f"-法源候选：{'\u3001'.join(item['authority_ids']) or '待研究'}",
            "-结论：待执业律师判断",
            "",
        ])
    lines.extend(["## 原始来源核验", ""])
    for source in result["sources"]:
        lines.append(f"- {source['source_id']}：{source['source_locator']}；SHA-256 `{source['sha256']}`；{source['verification_status']}")
    lines.extend(["", "## 人工决策队列", ""])
    lines.extend([f"- {item['action_id']}：{item['description']}（不得自动执行）" for item in result["human_decision_queue"]] or ["- 无已录入不利行动，仍需律师复核。"])
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
    parser = argparse.ArgumentParser(description="生成劳动用工全周期审查工作簿。")
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
