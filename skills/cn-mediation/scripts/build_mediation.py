#!/usr/bin/env python3
"""确定性生成调解方案工作台；原子新建 JSON 与 Markdown，拒绝覆盖。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = SKILL_DIR / "schemas" / "mediation-input.schema.json"
OUTPUT_SCHEMA = SKILL_DIR / "schemas" / "mediation-output.schema.json"
REQUIRED_CLAUSES = ("confidentiality", "performance", "default", "dispute_resolution")
LEAK_MARKERS = ("底线", "最低接受", "最高可付", "最高授权", "内部授权", "谈判目标")


class InputError(ValueError):
    """输入、Schema 或安全门禁错误。"""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"重复 JSON 键：{key}")
        result[key] = value
    return result


def load_input(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates, parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"无效 UTF-8 JSON：{exc}") from exc
    schema = json.loads(INPUT_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise InputError(f"Schema 校验失败 {location}：{first.message}")
    ids = [item["proposal_id"] for item in data["proposals"]]
    if len(ids) != len(set(ids)):
        raise InputError("proposal_id 不得重复")
    return data, raw


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def _authority_status(amount: Decimal, authority: dict[str, Any]) -> bool:
    if authority["amount_direction"] == "receive_at_least":
        return amount >= authority["limit_amount"]
    return amount <= authority["limit_amount"]


def _public_leaks(proposal: dict[str, Any]) -> list[str]:
    text = proposal["public_offer_text"]
    leaks = [f"对外预览包含内部标记“{marker}”" for marker in LEAK_MARKERS if marker in text]
    internal = proposal["internal_notes"].strip()
    if len(internal) >= 6 and internal in text:
        leaks.append("对外预览原样包含内部备注")
    return leaks


def build_workbench(data: dict[str, Any], raw: bytes) -> dict[str, Any]:
    authority = data["authority"]
    allowed_terms = {item["term_key"]: set(item["allowed_values"]) for item in authority["non_monetary_authorizations"]}
    blockers: list[str] = []
    if not authority["confirmed_by_client"]:
        blockers.append("当事人未确认调解授权边界")

    comparison: list[dict[str, Any]] = []
    previews: list[dict[str, Any]] = []
    for proposal in data["proposals"]:
        item_blockers: list[str] = []
        same_currency = proposal["currency"] == authority["currency"]
        within_amount = same_currency and _authority_status(proposal["amount"], authority)
        if not same_currency:
            item_blockers.append("方案币种与授权币种不一致，未提供已核验换算依据")
        elif not within_amount:
            item_blockers.append("方案金额超出当事人明示授权边界")

        unauthorized_terms: list[str] = []
        for term in proposal["non_monetary_terms"]:
            if term["term_key"] not in allowed_terms or term["value"] not in allowed_terms[term["term_key"]]:
                unauthorized_terms.append(term["term_key"])
            if term["term_key"] in authority["forbidden_commitments"]:
                unauthorized_terms.append(term["term_key"])
        unauthorized_terms = sorted(set(unauthorized_terms))
        if unauthorized_terms:
            item_blockers.append("存在未授权或禁止的非金额条件：" + "、".join(unauthorized_terms))

        categories = {clause["category"] for clause in proposal["clauses"]}
        missing = [category for category in REQUIRED_CLAUSES if category not in categories]
        if missing:
            item_blockers.append("协议条款清单缺失：" + "、".join(missing))

        leak_blockers = _public_leaks(proposal)
        item_blockers.extend(leak_blockers)
        schedule_total = sum((entry["amount"] for entry in proposal["payment_schedule"]), Decimal("0"))
        if schedule_total != proposal["amount"]:
            item_blockers.append("分期金额合计与方案总额不一致")
        blockers.extend(f"{proposal['proposal_id']}：{message}" for message in item_blockers)

        comparison.append({
            "proposal_id": proposal["proposal_id"],
            "label": proposal["label"],
            "amount": _plain(proposal["amount"]),
            "currency": proposal["currency"],
            "distance_from_target": _plain(abs(proposal["amount"] - authority["target_amount"])),
            "installment_count": len(proposal["payment_schedule"]),
            "within_amount_authority": within_amount,
            "unauthorized_non_monetary_terms": unauthorized_terms,
            "clause_checklist": {category: (category in categories) for category in REQUIRED_CLAUSES},
            "blockers": item_blockers,
        })
        previews.append({
            "proposal_id": proposal["proposal_id"],
            "text": proposal["public_offer_text"],
            "preview_state": "blocked" if leak_blockers else "lawyer_review_required",
            "auto_send": False,
        })

    return {
        "schema_version": "1.0",
        "artifact_state": "lawyer_review_required",
        "matter": _plain(data["matter"]),
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "internal_authority": _plain(authority),
        "proposal_comparison": comparison,
        "external_previews": previews,
        "action_controls": {"auto_send": False, "auto_sign": False, "auto_submit": False, "external_use_permitted": False},
        "blockers": blockers,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 调解方案内部复核工作台",
        "",
        f"-案件标识：{result['matter']['matter_id']}",
        f"-基准日：{result['matter']['as_of_date']}",
        "-文件状态：待执业律师复核",
        "-行为限制：不得自动发送、签署或提交",
        "",
        "## 方案比较",
        "",
        "|方案|金额|与目标差额|分期数|金额授权|阻断数|",
        "|---|---:|---:|---:|---|---:|",
    ]
    for item in result["proposal_comparison"]:
        authority_label = "范围内" if item["within_amount_authority"] else "超边界"
        lines.append(f"|{item['label']}|{item['amount']} {item['currency']}|{item['distance_from_target']}|{item['installment_count']}|{authority_label}|{len(item['blockers'])}|")
    lines.extend(["", "## 条款与授权检查", ""])
    for item in result["proposal_comparison"]:
        lines.extend([f"### {item['label']}", ""])
        for key, present in item["clause_checklist"].items():
            lines.append(f"- {key}：{'已录入' if present else '缺失'}")
        if item["unauthorized_non_monetary_terms"]:
            lines.append("- 未授权非金额条件：" + "、".join(item["unauthorized_non_monetary_terms"]))
        for blocker in item["blockers"]:
            lines.append(f"- 阻断：{blocker}")
        lines.append("")
    lines.extend(["## 脱敏对外预览（仍待审查）", ""])
    for preview in result["external_previews"]:
        lines.extend([f"### {preview['proposal_id']}", "", preview["text"], "", f"预览状态：{preview['preview_state']}", ""])
    lines.extend(["## 全局阻断项", ""])
    lines.extend([f"- {item}" for item in result["blockers"]] or ["- 无程序阻断；仍须律师和当事人复核。"])
    return "\n".join(lines) + "\n"


def write_pair_atomic(json_path: Path, json_bytes: bytes, md_path: Path, md_bytes: bytes) -> None:
    if json_path == md_path:
        raise InputError("JSON 与 Markdown 输出路径不得相同")
    for path in (json_path, md_path):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"输出已存在，拒绝覆盖：{path}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"输出目录不存在：{path.parent}")
    temps: list[Path] = []
    linked: list[Path] = []
    try:
        for path, payload in ((json_path, json_bytes), (md_path, md_bytes)):
            descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            temp = Path(name)
            temps.append(temp)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        for temp, target in zip(temps, (json_path, md_path), strict=True):
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
    parser = argparse.ArgumentParser(description="构建中国法律调解方案工作台。")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    try:
        data, raw = load_input(args.input)
        result = build_workbench(data, raw)
        output_schema = json.loads(OUTPUT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(output_schema).validate(result)
        json_bytes = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        write_pair_atomic(args.json_output, json_bytes, args.markdown_output, render_markdown(result).encode("utf-8"))
    except (InputError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "artifact_state": "lawyer_review_required", "json_output": str(args.json_output), "markdown_output": str(args.markdown_output), "blocker_count": len(result["blockers"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
