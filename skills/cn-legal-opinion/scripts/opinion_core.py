#!/usr/bin/env python3
"""中国法律意见分析底稿的共享验证、门禁和原子输出逻辑。"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


MAX_INPUT_BYTES = 8 * 1024 * 1024
SKILL_DIR = Path(__file__).resolve().parent.parent
INPUT_SCHEMA = SKILL_DIR / "schemas" / "opinion-input.schema.json"
OUTPUT_SCHEMA = SKILL_DIR / "schemas" / "opinion-output.schema.json"


class InputError(ValueError):
    """输入或输出目标无法安全处理。"""


def load_json_file(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value)
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise InputError(f"输入文件不存在：{path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise InputError("拒绝读取符号链接输入。")
    if not stat.S_ISREG(info.st_mode):
        raise InputError("输入必须是普通 JSON 文件。")
    if info.st_size > MAX_INPUT_BYTES:
        raise InputError(f"输入超过 {MAX_INPUT_BYTES} 字节限制。")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise InputError("输入必须使用 UTF-8 编码。") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(value, dict):
        raise InputError("JSON 顶层必须是对象。")
    return value


def _schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_path(error: Any) -> str:
    return "$" + "".join(
        f"[{part}]" if isinstance(part, int) else f".{part}"
        for part in error.absolute_path
    )


def schema_errors(data: dict[str, Any], *, output: bool = False) -> list[str]:
    validator = Draft202012Validator(
        _schema(OUTPUT_SCHEMA if output else INPUT_SCHEMA),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))
    return [f"{_json_path(error)}: {error.message}" for error in errors]


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def gate_checks(data: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """返回（结构错误、全局阻断项、警告）。"""
    fatal = schema_errors(data)
    if fatal:
        return fatal, [], []
    blockers: list[str] = []
    warnings: list[str] = []

    collections = [
        ("question_id", data["questions"]), ("fact_id", data["facts"]),
        ("assumption_id", data["assumptions"]), ("limitation_id", data["limitations"]),
        ("authority_id", data["authorities"]), ("proposition_id", data["propositions"]),
        ("conclusion_id", data["conclusion_drafts"]),
    ]
    for key, items in collections:
        duplicates = _duplicates([item[key] for item in items])
        if duplicates:
            fatal.append(f"存在重复 {key}：{', '.join(duplicates)}")

    questions = {item["question_id"]: item for item in data["questions"]}
    facts = {item["fact_id"]: item for item in data["facts"]}
    assumptions = {item["assumption_id"]: item for item in data["assumptions"]}
    authorities = {item["authority_id"]: item for item in data["authorities"]}

    conflicted = sorted(item["fact_id"] for item in data["facts"] if item["status"] == "conflicted")
    if conflicted:
        blockers.append(f"存在冲突事实：{', '.join(conflicted)}")
    critical_unconfirmed = sorted(
        item["assumption_id"] for item in data["assumptions"]
        if item["critical"] and item["status"] != "confirmed"
    )
    if critical_unconfirmed:
        blockers.append(f"存在未确认关键假设：{', '.join(critical_unconfirmed)}")

    as_of = date.fromisoformat(data["as_of_date"])
    for authority in data["authorities"]:
        if date.fromisoformat(authority["verified_on"]) > as_of:
            blockers.append(f"法源 {authority['authority_id']} 核验日晚于意见时点。")
        if authority["verification_status"] != "verified_official":
            blockers.append(f"法源 {authority['authority_id']} 未完成官方全文核验。")
        if authority["effect_status"] != "effective":
            blockers.append(f"法源 {authority['authority_id']} 效力状态为 {authority['effect_status']}。")

    def validate_trace(item: dict[str, Any], item_name: str) -> None:
        if item["question_id"] not in questions:
            fatal.append(f"{item_name} 引用未登记问题：{item['question_id']}")
        missing_facts = sorted(set(item["fact_ids"]) - set(facts))
        missing_authorities = sorted(set(item["authority_ids"]) - set(authorities))
        if missing_facts:
            fatal.append(f"{item_name} 引用未登记事实：{', '.join(missing_facts)}")
        if missing_authorities:
            fatal.append(f"{item_name} 引用未登记法源：{', '.join(missing_authorities)}")

    stances: dict[str, set[str]] = {question_id: set() for question_id in questions}
    for proposition in data["propositions"]:
        validate_trace(proposition, f"分析命题 {proposition['proposition_id']}")
        if proposition["question_id"] in stances:
            stances[proposition["question_id"]].add(proposition["stance"])
    for question_id, values in stances.items():
        if "supporting" not in values:
            warnings.append(f"问题 {question_id} 缺少支持性分析命题。")
        if "adverse" not in values:
            warnings.append(f"问题 {question_id} 缺少反对或不利分析命题。")

    for conclusion in data["conclusion_drafts"]:
        validate_trace(conclusion, f"结论草案 {conclusion['conclusion_id']}")
        missing_assumptions = sorted(set(conclusion["dependency_assumption_ids"]) - set(assumptions))
        if missing_assumptions:
            fatal.append(f"结论草案 {conclusion['conclusion_id']} 引用未登记假设：{', '.join(missing_assumptions)}")

    if data["mode"] == "training_fixture":
        warnings.append("当前为教学测试模式，不得作为真实法律意见。")
    return sorted(set(fatal)), sorted(set(blockers)), sorted(set(warnings))


def _conclusion_blockers(
    conclusion: dict[str, Any],
    facts: dict[str, dict[str, Any]],
    assumptions: dict[str, dict[str, Any]],
    authorities: dict[str, dict[str, Any]],
    global_blockers: list[str],
    as_of: date,
) -> list[str]:
    blockers = list(global_blockers)
    for fact_id in conclusion["fact_ids"]:
        status = facts[fact_id]["status"]
        if status != "confirmed":
            blockers.append(f"结论依赖事实 {fact_id} 状态为 {status}。")
    for assumption_id in conclusion["dependency_assumption_ids"]:
        if assumptions[assumption_id]["status"] != "confirmed":
            blockers.append(f"结论依赖假设 {assumption_id} 尚未确认。")
    for authority_id in conclusion["authority_ids"]:
        authority = authorities[authority_id]
        if authority["verification_status"] != "verified_official":
            blockers.append(f"结论依赖法源 {authority_id} 未完成官方核验。")
        if authority["effect_status"] != "effective":
            blockers.append(f"结论依赖法源 {authority_id} 非现行有效。")
        if date.fromisoformat(authority["verified_on"]) > as_of:
            blockers.append(f"结论依赖法源 {authority_id} 在意见时点后才核验。")
    return sorted(set(blockers))


def build_workpaper(data: dict[str, Any]) -> dict[str, Any]:
    fatal, blockers, warnings = gate_checks(data)
    if fatal:
        raise InputError("输入验证失败：" + "；".join(fatal))
    facts = {item["fact_id"]: item for item in data["facts"]}
    assumptions = {item["assumption_id"]: item for item in data["assumptions"]}
    authorities = {item["authority_id"]: item for item in data["authorities"]}
    as_of = date.fromisoformat(data["as_of_date"])
    conclusions = []
    for draft in sorted(data["conclusion_drafts"], key=lambda item: item["conclusion_id"]):
        item = dict(draft)
        item_blockers = _conclusion_blockers(draft, facts, assumptions, authorities, blockers, as_of)
        item["status"] = "blocked" if item_blockers else "provisional_for_lawyer_review"
        item["blockers"] = item_blockers
        conclusions.append(item)

    verified_authorities = sorted(
        (item for item in data["authorities"] if item["verification_status"] == "verified_official" and item["effect_status"] == "effective" and date.fromisoformat(item["verified_on"]) <= as_of),
        key=lambda item: item["authority_id"],
    )
    verified_ids = {item["authority_id"] for item in verified_authorities}
    workpaper = {
        "schema_version": "1.0", "matter_id": data["matter_id"], "mode": data["mode"],
        "jurisdiction": data["jurisdiction"], "as_of_date": data["as_of_date"],
        "artifact_state": "lawyer_review_required", "formal_opinion_issued": False,
        "questions": sorted(data["questions"], key=lambda item: item["question_id"]),
        "confirmed_facts": sorted((item for item in data["facts"] if item["status"] == "confirmed"), key=lambda item: item["fact_id"]),
        "unresolved_facts": sorted((item for item in data["facts"] if item["status"] != "confirmed"), key=lambda item: item["fact_id"]),
        "assumptions": sorted(data["assumptions"], key=lambda item: item["assumption_id"]),
        "limitations": sorted(data["limitations"], key=lambda item: item["limitation_id"]),
        "verified_authorities": verified_authorities,
        "other_authorities": sorted((item for item in data["authorities"] if item["authority_id"] not in verified_ids), key=lambda item: item["authority_id"]),
        "propositions": sorted(data["propositions"], key=lambda item: item["proposition_id"]),
        "conclusions": conclusions, "blockers": blockers, "warnings": warnings,
    }
    output_errors = schema_errors(workpaper, output=True)
    if output_errors:
        raise RuntimeError("内部输出未通过 Schema：" + "；".join(output_errors))
    return workpaper


def render_markdown(workpaper: dict[str, Any]) -> str:
    lines = [
        "# 中国法律意见分析——律师复核底稿", "",
        f"- 项目编号：{workpaper['matter_id']}", f"- 法域：{workpaper['jurisdiction']}",
        f"- 意见时点：{workpaper['as_of_date']}", "- 底稿状态：律师复核必需", "- 正式意见已签发：否", "",
        "## 问题", "",
    ]
    lines.extend(f"- {item['question_id']}：{item['text']}" for item in workpaper["questions"])
    lines.extend(["", "## 已确认事实", ""])
    lines.extend([f"- {item['fact_id']}：{item['statement']}" for item in workpaper["confirmed_facts"]] or ["- 无。"])
    lines.extend(["", "## 冲突或未核验事实", ""])
    lines.extend([f"- {item['fact_id']}：{item['statement']}（{item['status']}）" for item in workpaper["unresolved_facts"]] or ["- 无。"])
    lines.extend(["", "## 假设", ""])
    lines.extend([f"- {item['assumption_id']}：{item['statement']}（关键：{item['critical']}；{item['status']}）" for item in workpaper["assumptions"]] or ["- 无。"])
    lines.extend(["", "## 限制", ""])
    lines.extend([f"- {item['limitation_id']}：{item['statement']}" for item in workpaper["limitations"]] or ["- 无。"])
    lines.extend(["", "## 正反分析命题", ""])
    for item in workpaper["propositions"]:
        lines.extend([f"### {item['proposition_id']}（{item['stance']}）", "", item["statement"], "", f"事实：{'、'.join(item['fact_ids'])}；法源：{'、'.join(item['authority_ids'])}", ""])
    lines.extend(["## 结论草案", ""])
    for item in workpaper["conclusions"]:
        lines.extend([f"### {item['conclusion_id']}（{item['status']}）", "", item["statement"], "", f"事实：{'、'.join(item['fact_ids'])}；法源：{'、'.join(item['authority_ids'])}", ""])
        if item["blockers"]:
            lines.extend(["阻断项：", ""] + [f"- {value}" for value in item["blockers"]] + [""])
    lines.extend(["## 全局阻断项", ""])
    lines.extend([f"- {item}" for item in workpaper["blockers"]] or ["- 无额外结构性阻断项；结论仍仅供律师复核。"])
    lines.extend(["", "> 本文件不是正式法律意见书，不得用于签章或对外发送。", ""])
    return "\n".join(lines)


def atomic_write_workpaper(workpaper: dict[str, Any], output_value: str | Path) -> Path:
    output = Path(output_value)
    if output.exists() or output.is_symlink():
        raise InputError(f"输出目标已存在，拒绝覆盖：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (temp / "opinion-workpaper.json").write_text(json.dumps(workpaper, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (temp / "opinion-workpaper.md").write_text(render_markdown(workpaper), encoding="utf-8")
        os.replace(temp, output)
    except Exception:
        for child in temp.iterdir() if temp.exists() else []:
            child.unlink()
        if temp.exists():
            temp.rmdir()
        raise
    return output
