#!/usr/bin/env python3
"""确定性生成严格隔离的谈判内部工作簿与对外预览。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = SKILL_DIR / "schemas" / "negotiation-input.schema.json"
WORKBOOK_SCHEMA = SKILL_DIR / "schemas" / "negotiation-workbook.schema.json"
EXTERNAL_SCHEMA = SKILL_DIR / "schemas" / "external-preview.schema.json"
LEAK_MARKERS = (
    "底线",
    "batna",
    "授权上限",
    "授权下限",
    "最高可付",
    "最低可收",
    "内部授权",
    "内部目标",
    "内部优先级",
    "内部评分",
    "内部备注",
)
FORBIDDEN_EXTERNAL_KEYS = {
    "authorization",
    "bottom_lines",
    "batna",
    "objectives",
    "issue_priorities",
    "evaluation_criteria",
    "proposal_assessments",
    "internal_strategy",
    "internal_notes",
    "weighted_score",
}
ACTION_CONTROLS = {
    "auto_send": False,
    "auto_sign": False,
    "auto_submit": False,
    "auto_commit": False,
    "external_use_permitted": False,
}


class InputError(ValueError):
    """输入、Schema 或安全门禁错误。"""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"重复 JSON 键：{key}")
        result[key] = value
    return result


def _schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_input(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_float=Decimal,
        )
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


def _unique_ids(items: Iterable[dict[str, Any]], key: str, label: str) -> set[str]:
    ids = [item[key] for item in items]
    if len(ids) != len(set(ids)):
        raise InputError(f"{label}中 {key} 不得重复")
    return set(ids)


def _require_refs(values: Iterable[str], allowed: set[str], label: str) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise InputError(f"{label}引用未定义编号：{'\u3001'.join(unknown)}")


def validate_semantics(data: dict[str, Any]) -> None:
    internal = data["internal_strategy"]
    external = data["external_workspace"]
    authorization = internal["authorization"]
    if not authorization["confirmed_by_client"] or authorization["confirmed_at"] is None:
        raise InputError("客户授权未明示确认或缺少确认日期")

    issue_ids = _unique_ids(external["issues"], "issue_id", "对外议题")
    proposal_ids = _unique_ids(external["proposals"], "proposal_id", "对外提案")
    criterion_ids = _unique_ids(internal["evaluation_criteria"], "criterion_id", "评估标准")
    _unique_ids(internal["objectives"], "objective_id", "内部目标")
    _unique_ids(internal["batna"], "scenario_id", "BATNA")
    _unique_ids(external["meeting_minutes"]["tentative_items"], "item_id", "暂定事项")

    priorities = _unique_ids(internal["issue_priorities"], "issue_id", "议题优先级")
    if priorities != issue_ids:
        raise InputError("议题优先级必须与对外议题一一对应")
    _require_refs((item["issue_id"] for item in internal["bottom_lines"]), issue_ids, "底线")
    _require_refs((item["issue_id"] for item in authorization["monetary_limits"]), issue_ids, "授权金额")

    assessment_ids = _unique_ids(internal["proposal_assessments"], "proposal_id", "方案评估")
    if assessment_ids != proposal_ids:
        raise InputError("内部方案评估必须与对外提案一一对应")
    if sum(item["weight"] for item in internal["evaluation_criteria"]) != Decimal("100"):
        raise InputError("评估标准权重合计必须等于 100")

    for assessment in internal["proposal_assessments"]:
        score_ids = _unique_ids(assessment["scores"], "criterion_id", f"方案 {assessment['proposal_id']} 评分")
        if score_ids != criterion_ids:
            raise InputError(f"方案 {assessment['proposal_id']} 必须对所有标准各评分一次")

    exchange_ids: list[str] = []
    for proposal in external["proposals"]:
        term_issue_ids = [item["issue_id"] for item in proposal["terms"]]
        if len(term_issue_ids) != len(set(term_issue_ids)):
            raise InputError(f"提案 {proposal['proposal_id']} 不得对同一议题重复录入条件")
        _require_refs(term_issue_ids, issue_ids, f"提案 {proposal['proposal_id']} 条件")
        for exchange in proposal["conditional_exchanges"]:
            exchange_ids.append(exchange["exchange_id"])
            _require_refs(
                (exchange["give_issue_id"], exchange["receive_issue_id"]),
                issue_ids,
                f"交换 {exchange['exchange_id']}",
            )
    if len(exchange_ids) != len(set(exchange_ids)):
        raise InputError("exchange_id 不得重复")

    minutes = external["meeting_minutes"]
    _require_refs((item["issue_id"] for item in minutes["discussion"]), issue_ids, "会议讨论")
    detect_external_leaks(data)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _sensitive_phrases(internal: dict[str, Any]) -> list[tuple[str, str]]:
    phrases: list[tuple[str, str]] = []

    def add(label: str, value: str) -> None:
        normalized = _normalize_text(value)
        if len(normalized) >= 6:
            phrases.append((label, normalized))

    for item in internal["objectives"]:
        add("内部目标", item["description"])
    add("授权备注", internal["authorization"]["scope_notes"])
    for value in internal["authorization"]["prohibited_commitments"]:
        add("禁止承诺", value)
    for item in internal["bottom_lines"]:
        add("底线", item["description"])
    for item in internal["batna"]:
        add("BATNA", item["description"])
        for assumption in item["assumptions"]:
            add("BATNA 假设", assumption)
    for item in internal["issue_priorities"]:
        add("优先级理由", item["reason"])
    for assessment in internal["proposal_assessments"]:
        add("方案内部备注", assessment["internal_notes"])
        for score in assessment["scores"]:
            add("方案评分理由", score["reason"])
    return phrases


def detect_external_leaks(data: dict[str, Any]) -> None:
    internal = data["internal_strategy"]
    external = data["external_workspace"]
    external_text = json.dumps(_plain(external), ensure_ascii=False, sort_keys=True)
    normalized_external = _normalize_text(external_text)
    leaks: list[str] = []
    for marker in LEAK_MARKERS:
        if _normalize_text(marker) in normalized_external:
            leaks.append(f"对外工作区包含内部标记：{marker}")
    for label, phrase in _sensitive_phrases(internal):
        if phrase in normalized_external:
            leaks.append(f"对外工作区原样或规范化后包含{label}")
    for limit in internal["authorization"]["monetary_limits"]:
        amount = _decimal_text(limit["amount"])
        normalized_numbers = re.sub(r"[,，\s]", "", unicodedata.normalize("NFKC", external_text))
        amount_pattern = rf"(?<![0-9]){re.escape(amount)}(?:\.0+)?(?![0-9])"
        amount_value = Decimal(str(limit["amount"]))
        compact_patterns = [amount_pattern]
        if amount_value == amount_value.to_integral():
            for unit_value, unit_label in ((Decimal("10000"), "万"), (Decimal("100000000"), "亿")):
                compact = amount_value / unit_value
                if compact == compact.to_integral() and compact > 0:
                    compact_patterns.append(rf"(?<![0-9]){re.escape(format(compact, 'f'))}(?:\.0+)?{unit_label}(?:元)?")
        if any(re.search(pattern, normalized_numbers) for pattern in compact_patterns):
            leaks.append(f"对外工作区包含已知授权金额：{limit['issue_id']}")
    if leaks:
        raise InputError("；".join(dict.fromkeys(leaks)))


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def _decimal_text(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def build_external_preview(data: dict[str, Any]) -> dict[str, Any]:
    workspace = data["external_workspace"]
    proposals = []
    for proposal in workspace["proposals"]:
        proposals.append({
            "proposal_id": proposal["proposal_id"],
            "label": proposal["label"],
            "terms": [
                {"issue_id": item["issue_id"], "offer_text": item["offer_text"], "status": item["status"]}
                for item in proposal["terms"]
            ],
            "public_rationale": proposal["public_rationale"],
            "conditional_exchanges": [
                {
                    "exchange_id": item["exchange_id"],
                    "give_issue_id": item["give_issue_id"],
                    "give_text": item["give_text"],
                    "receive_issue_id": item["receive_issue_id"],
                    "receive_text": item["receive_text"],
                    "condition_text": item["condition_text"],
                    "exchange_state": "proposed_conditional_exchange",
                }
                for item in proposal["conditional_exchanges"]
            ],
            "proposal_state": "lawyer_review_required",
        })

    minutes = workspace["meeting_minutes"]
    pending: list[dict[str, str]] = []
    for proposal in workspace["proposals"]:
        if proposal["requires_client_confirmation"]:
            pending.append({"source_type": "proposal", "source_id": proposal["proposal_id"], "summary": f"提案“{proposal['label']}”待客户确认"})
    for item in minutes["tentative_items"]:
        if item["status"] == "pending":
            pending.append({"source_type": "meeting_item", "source_id": item["item_id"], "summary": item["summary"]})
    for index, item in enumerate(minutes["next_steps"], start=1):
        if item["status"] == "pending":
            pending.append({"source_type": "next_step", "source_id": f"NEXT-{index:03d}", "summary": item["action"]})

    preview = {
        "schema_version": "1.0",
        "artifact_state": "lawyer_review_required",
        "external_reference": workspace["external_reference"],
        "as_of_date": data["matter"]["as_of_date"],
        "agenda": [
            {
                "issue_id": item["issue_id"],
                "label": item["label"],
                "public_position": item["public_position"],
                "questions": list(item["questions"]),
            }
            for item in workspace["issues"]
        ],
        "proposals": proposals,
        "meeting_minutes": {
            "meeting_id": minutes["meeting_id"],
            "meeting_date": minutes["meeting_date"],
            "participant_roles": list(minutes["participant_roles"]),
            "discussion": [
                {"issue_id": item["issue_id"], "summary": item["summary"]}
                for item in minutes["discussion"]
            ],
            "tentative_items": [
                {"item_id": item["item_id"], "summary": item["summary"], "status": item["status"]}
                for item in minutes["tentative_items"]
            ],
            "next_steps": [
                {
                    "action": item["action"],
                    "owner_role": item["owner_role"],
                    "due_date": item["due_date"],
                    "status": item["status"],
                }
                for item in minutes["next_steps"]
            ],
            "minutes_state": "record_only_not_commitment",
        },
        "pending_confirmations": pending,
        "disclosure_statement": "本文件仅为待执业律师复核的对外预览，不代表客户承诺，不得自动发送、签署或提交",
        "action_controls": dict(ACTION_CONTROLS),
    }
    assert_no_internal_keys(preview)
    Draft202012Validator(_schema(EXTERNAL_SCHEMA), format_checker=FormatChecker()).validate(preview)
    return preview


def assert_no_internal_keys(value: Any, path: str = "<root>") -> None:
    if isinstance(value, dict):
        forbidden = sorted(set(value) & FORBIDDEN_EXTERNAL_KEYS)
        if forbidden:
            raise InputError(f"对外预览出现禁止字段 {path}：{'\u3001'.join(forbidden)}")
        for key, child in value.items():
            assert_no_internal_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_internal_keys(child, f"{path}[{index}]")


def build_internal_workbook(data: dict[str, Any], raw: bytes, external_bytes: bytes) -> dict[str, Any]:
    internal = data["internal_strategy"]
    workspace = data["external_workspace"]
    labels = {item["issue_id"]: item["label"] for item in workspace["issues"]}
    proposal_labels = {item["proposal_id"]: item["label"] for item in workspace["proposals"]}
    criteria = {item["criterion_id"]: item for item in internal["evaluation_criteria"]}

    issue_plan = sorted(
        (
            {
                "issue_id": item["issue_id"],
                "label": labels[item["issue_id"]],
                "priority": int(item["priority"]),
                "reason": item["reason"],
            }
            for item in internal["issue_priorities"]
        ),
        key=lambda item: (item["priority"], item["issue_id"]),
    )

    comparison = []
    proposal_confirmation = {item["proposal_id"]: item["requires_client_confirmation"] for item in workspace["proposals"]}
    for assessment in internal["proposal_assessments"]:
        weighted = Decimal("0")
        score_rows = []
        for score in assessment["scores"]:
            criterion = criteria[score["criterion_id"]]
            contribution = Decimal(score["score"]) * Decimal(criterion["weight"]) / Decimal("100")
            weighted += contribution
            score_rows.append({
                "criterion_id": score["criterion_id"],
                "label": criterion["label"],
                "weight": int(criterion["weight"]),
                "score": int(score["score"]),
                "contribution": f"{contribution:.2f}",
                "reason": score["reason"],
            })
        comparison.append({
            "proposal_id": assessment["proposal_id"],
            "label": proposal_labels[assessment["proposal_id"]],
            "criterion_scores": score_rows,
            "weighted_score": f"{weighted:.2f}",
            "comparison_note": "仅供并列比较，不构成排名、推荐或结果预测",
            "requires_client_confirmation": proposal_confirmation[assessment["proposal_id"]],
            "internal_notes": assessment["internal_notes"],
        })

    external_preview = build_external_preview(data)
    if external_bytes != encode_json(external_preview):
        raise InputError("对外预览字节与白名单重建结果不一致")
    pending = list(external_preview["pending_confirmations"])
    blockers = [f"待客户确认：{item['source_id']}——{item['summary']}" for item in pending]
    workbook = {
        "schema_version": "1.0",
        "artifact_state": "lawyer_review_required",
        "internal_only": True,
        "external_use_permitted": False,
        "matter": _plain(data["matter"]),
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "internal_strategy": _plain(internal),
        "issue_plan": issue_plan,
        "proposal_comparison": comparison,
        "pending_confirmations": pending,
        "external_preview_sha256": hashlib.sha256(external_bytes).hexdigest(),
        "blockers": blockers,
        "action_controls": dict(ACTION_CONTROLS),
    }
    Draft202012Validator(_schema(WORKBOOK_SCHEMA), format_checker=FormatChecker()).validate(workbook)
    return workbook


def encode_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _normalized_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def write_pair_atomic(first_path: Path, first_bytes: bytes, second_path: Path, second_bytes: bytes) -> None:
    if _normalized_path(first_path) == _normalized_path(second_path):
        raise InputError("内部与对外输出路径不得相同")
    paths = (first_path, second_path)
    for path in paths:
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"输出已存在，拒绝覆盖：{path}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"输出目录不存在：{path.parent}")

    temporary: list[Path] = []
    linked: list[Path] = []
    try:
        for target, payload in ((first_path, first_bytes), (second_path, second_bytes)):
            descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temp_path = Path(name)
            temporary.append(temp_path)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        for temp_path, target in zip(temporary, paths, strict=True):
            os.link(temp_path, target)
            linked.append(target)
    except Exception:
        for path in linked:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成谈判内部工作簿与独立对外预览。")
    parser.add_argument("input", type=Path)
    parser.add_argument("--internal-output", required=True, type=Path)
    parser.add_argument("--external-output", required=True, type=Path)
    args = parser.parse_args()
    try:
        input_normalized = _normalized_path(args.input)
        if input_normalized in {_normalized_path(args.internal_output), _normalized_path(args.external_output)}:
            raise InputError("输入与输出路径不得相同")
        data, raw = load_input(args.input)
        external = build_external_preview(data)
        external_bytes = encode_json(external)
        workbook = build_internal_workbook(data, raw, external_bytes)
        write_pair_atomic(args.internal_output, encode_json(workbook), args.external_output, external_bytes)
    except (InputError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({
        "ok": True,
        "artifact_state": "lawyer_review_required",
        "internal_output": str(args.internal_output),
        "external_output": str(args.external_output),
        "pending_confirmation_count": len(external["pending_confirmations"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
