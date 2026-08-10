#!/usr/bin/env python3
"""确定性生成仲裁案件工作台；不选机构、仲裁员或期限。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = SKILL_DIR / "schemas" / "arbitration-input.schema.json"
OUTPUT_SCHEMA = SKILL_DIR / "schemas" / "arbitration-output.schema.json"


class InputError(ValueError):
    """仲裁工作台输入错误。"""


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"重复 JSON 键：{key}")
        result[key] = value
    return result


def load_input(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
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
    for field, key in (
        ("authorities", "authority_id"), ("claims", "claim_id"),
        ("jurisdiction_objections", "objection_id"), ("arbitrator_disclosures", "disclosure_id"),
        ("evidence", "evidence_id"), ("schedule", "event_id"),
    ):
        ids = [item[key] for item in data[field]]
        if len(ids) != len(set(ids)):
            raise InputError(f"{key} 不得重复")
    return data, raw


def build_workbench(data: dict[str, Any], raw: bytes) -> dict[str, Any]:
    blockers: list[str] = []
    as_of = data["matter"]["as_of_date"]
    agreement = data["arbitration_agreement"]
    institution = data["institution"]

    agreement_blockers: list[str] = []
    if agreement["review_status"] != "human_checked":
        agreement_blockers.append("仲裁协议未经人工核对")
    if agreement["conflicts"]:
        agreement_blockers.append("仲裁协议存在待处理文本冲突")
    for field, label in (("institution_name_as_written", "机构名称"), ("seat_as_written", "仲裁地"), ("scope_as_written", "适用范围")):
        if not agreement[field].strip():
            agreement_blockers.append(f"仲裁协议中的{label}尚待确认")
    blockers.extend(agreement_blockers)

    institution_blockers: list[str] = []
    if institution["selection_status"] != "confirmed":
        institution_blockers.append("仲裁机构尚未由协议或当事人确认，脚本不代为选择")
    if institution["verified_on"] > as_of:
        institution_blockers.append("机构来源核验日期晚于工作台基准日")
    blockers.extend(institution_blockers)

    authority_review: list[dict[str, Any]] = []
    known_authorities = {item["authority_id"] for item in data["authorities"]}
    for authority in data["authorities"]:
        item_blockers: list[str] = []
        if authority["verified_on"] > as_of:
            item_blockers.append("核验日期晚于工作台基准日")
        if authority["effect_status"] != "effective":
            item_blockers.append("效力状态不是 effective")
        if authority["applicability_status"] != "confirmed":
            item_blockers.append("本案适用状态未确认")
        blockers.extend(f"{authority['authority_id']}：{message}" for message in item_blockers)
        authority_review.append({**authority, "blockers": item_blockers})

    claim_register: list[dict[str, Any]] = []
    evidence_ids = {item["evidence_id"] for item in data["evidence"]}
    for claim in data["claims"]:
        item_blockers: list[str] = []
        if claim["review_status"] != "human_checked":
            item_blockers.append("请求未经人工复核")
        if not claim["fact_ids"]:
            item_blockers.append("缺少事实标识")
        missing_evidence = sorted(set(claim["evidence_ids"]) - evidence_ids)
        missing_authorities = sorted(set(claim["authority_ids"]) - known_authorities)
        if not claim["evidence_ids"] or missing_evidence:
            item_blockers.append("证据引用缺失或无法对应")
        if not claim["authority_ids"] or missing_authorities:
            item_blockers.append("依据引用缺失或无法对应")
        blockers.extend(f"{claim['claim_id']}：{message}" for message in item_blockers)
        claim_register.append({**claim, "blockers": item_blockers})

    jurisdiction_register: list[dict[str, Any]] = []
    for objection in data["jurisdiction_objections"]:
        item_blockers: list[str] = []
        if objection["review_status"] != "human_checked":
            item_blockers.append("管辖异议未经人工复核")
        if not objection["evidence_ids"] or not objection["authority_ids"]:
            item_blockers.append("管辖异议的证据或依据引用缺失")
        if set(objection["evidence_ids"]) - evidence_ids or set(objection["authority_ids"]) - known_authorities:
            item_blockers.append("管辖异议引用无法对应到登记项")
        blockers.extend(f"{objection['objection_id']}：{message}" for message in item_blockers)
        jurisdiction_register.append({**objection, "blockers": item_blockers})

    disclosure_register: list[dict[str, Any]] = []
    for disclosure in data["arbitrator_disclosures"]:
        item_blockers: list[str] = []
        if disclosure["assessment_status"] != "human_assessed":
            item_blockers.append("仲裁员披露尚未由律师评估")
        if not disclosure["response_plan"].strip():
            item_blockers.append("披露后处理方案待确认")
        blockers.extend(f"{disclosure['disclosure_id']}：{message}" for message in item_blockers)
        disclosure_register.append({**disclosure, "blockers": item_blockers, "automatic_recommendation": None})

    evidence_register: list[dict[str, Any]] = []
    for evidence in data["evidence"]:
        item_blockers: list[str] = []
        if evidence["review_status"] != "human_checked" or not evidence["proof_purpose"].strip():
            item_blockers.append("证据的证明目的或人工复核尚未完成")
        blockers.extend(f"{evidence['evidence_id']}：{message}" for message in item_blockers)
        evidence_register.append({**evidence, "blockers": item_blockers, "admissibility_decision": None})

    schedule_register: list[dict[str, Any]] = []
    valid_sources = known_authorities | {institution["institution_id"]}
    for event in data["schedule"]:
        item_blockers: list[str] = []
        if event["date"] is None or not event["date_basis"].strip():
            item_blockers.append("日程事件缺少明示日期或日期依据，本脚本不自动计算")
        if event["source_ref"] not in valid_sources:
            item_blockers.append("日程来源无法对应已核验机构或依据")
        if event["review_status"] != "human_checked":
            item_blockers.append("日程未经人工复核")
        blockers.extend(f"{event['event_id']}：{message}" for message in item_blockers)
        schedule_register.append({**event, "blockers": item_blockers, "calculated_by_script": False})

    return {
        "schema_version": "1.0",
        "artifact_state": "lawyer_review_required",
        "matter": data["matter"],
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "agreement_review": {**agreement, "blockers": agreement_blockers, "validity_decision": None},
        "institution_review": {**institution, "blockers": institution_blockers, "selected_by_script": False},
        "authority_review": authority_review,
        "claim_register": claim_register,
        "jurisdiction_register": jurisdiction_register,
        "disclosure_register": disclosure_register,
        "evidence_register": evidence_register,
        "schedule_register": schedule_register,
        "action_controls": {
            "auto_select_institution": False, "auto_select_arbitrator": False,
            "auto_calculate_deadlines": False, "auto_send": False, "auto_sign": False, "auto_submit": False,
        },
        "blockers": blockers,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 中国大陆仲裁案件复核工作台", "",
        f"-案件标识：{result['matter']['matter_id']}",
        f"-基准日：{result['matter']['as_of_date']}",
        "-文件状态：待执业律师复核",
        "-禁止动作：不自动选机构、选仲裁员、计算期限、发送、签署或提交", "",
        "## 仲裁协议与机构", "",
        f"-协议人工核对：{result['agreement_review']['review_status']}",
        f"-机构：{result['institution_review']['name']}",
        f"-机构确认：{result['institution_review']['selection_status']}",
        f"-机构来源：{result['institution_review']['official_url']}", "",
        "## 法源与规则版本", "",
        "|标识|类型|版本|核验日|效力|适用|阻断数|", "|---|---|---|---|---|---|---:|",
    ]
    for item in result["authority_review"]:
        lines.append(f"|{item['authority_id']}|{item['kind']}|{item['version']}|{item['verified_on']}|{item['effect_status']}|{item['applicability_status']}|{len(item['blockers'])}|")
    for heading, key, id_key, label_key in (
        ("请求与反请求", "claim_register", "claim_id", "request"),
        ("管辖异议", "jurisdiction_register", "objection_id", "issue"),
        ("仲裁员披露", "disclosure_register", "disclosure_id", "disclosed_fact"),
        ("证据", "evidence_register", "evidence_id", "name"),
        ("程序日程", "schedule_register", "event_id", "label"),
    ):
        lines.extend(["", f"## {heading}", ""])
        for item in result[key]:
            lines.append(f"- {item[id_key]}：{item[label_key]}；阻断数 {len(item['blockers'])}")
    lines.extend(["", "## 全局阻断项", ""])
    lines.extend([f"- {item}" for item in result["blockers"]] or ["- 无结构化阻断；仍须执业律师全面复核。"])
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
    parser = argparse.ArgumentParser(description="构建中国大陆仲裁案件工作台。")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    try:
        data, raw = load_input(args.input)
        result = build_workbench(data, raw)
        Draft202012Validator(json.loads(OUTPUT_SCHEMA.read_text(encoding="utf-8"))).validate(result)
        json_bytes = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        write_pair_atomic(args.json_output, json_bytes, args.markdown_output, render_markdown(result).encode("utf-8"))
    except (InputError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "artifact_state": "lawyer_review_required", "blocker_count": len(result["blockers"]), "json_output": str(args.json_output), "markdown_output": str(args.markdown_output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
