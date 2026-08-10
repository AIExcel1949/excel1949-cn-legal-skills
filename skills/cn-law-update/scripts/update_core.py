#!/usr/bin/env python3
"""中国法律更新比对的共享验证、差异和报告逻辑。"""

from __future__ import annotations

import difflib
import hashlib
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
SCHEMA_PATH = SKILL_DIR / "schemas" / "law-update-input.schema.json"
REPORT_SCHEMA_PATH = SKILL_DIR / "schemas" / "law-update-report.schema.json"
IMPACT_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class InputError(ValueError):
    """输入或结构无法安全处理。"""


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
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise InputError("输入必须使用 UTF-8 编码。") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(value, dict):
        raise InputError("JSON 顶层必须是对象。")
    return value


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_report_schema() -> dict[str, Any]:
    return json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _json_path(error: Any) -> str:
    if not error.absolute_path:
        return "$"
    return "$" + "".join(
        f"[{part}]" if isinstance(part, int) else f".{part}"
        for part in error.absolute_path
    )


def schema_errors(data: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.absolute_path))
    return [f"{_json_path(error)}: {error.message}" for error in errors]


def report_schema_errors(report: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(load_report_schema(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(report), key=lambda err: list(err.absolute_path))
    return [f"{_json_path(error)}: {error.message}" for error in errors]


def canonical_version_text(version: dict[str, Any]) -> str:
    parts: list[str] = []
    for unit in version.get("units", []):
        text = str(unit.get("text", "")).replace("\r\n", "\n").replace("\r", "\n").strip()
        parts.append(text)
    return "\n".join(parts)


def text_sha256(version: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_version_text(version).encode("utf-8")).hexdigest()


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def gate_checks(data: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """返回（致命结构错误、生产阻断项、警告）。"""
    fatal = schema_errors(data)
    if fatal:
        return fatal, [], []

    blockers: list[str] = []
    warnings: list[str] = []
    comparison_date = date.fromisoformat(data["comparison_date"])
    old_version = data["old_version"]
    new_version = data["new_version"]

    if old_version["version_id"] == new_version["version_id"]:
        fatal.append("新旧版本的 version_id 必须不同。")

    for label, version in (("旧版本", old_version), ("新版本", new_version)):
        unit_ids = [unit["unit_id"] for unit in version["units"]]
        duplicates = _duplicate_values(unit_ids)
        if duplicates:
            fatal.append(f"{label}存在重复 unit_id：{', '.join(duplicates)}")
        actual_hash = text_sha256(version)
        if actual_hash != version["text_sha256"]:
            blockers.append(
                f"{label}原文 SHA-256 不匹配：记录 {version['text_sha256']}，实际 {actual_hash}。"
            )
        if not version["full_text_checked"]:
            blockers.append(f"{label}未完成官方全文核验。")
        verified_on = date.fromisoformat(version["verified_on"])
        if verified_on > comparison_date:
            blockers.append(f"{label}核验日期晚于比对日。")

        source = version["source"]
        page_title = source.get("page_title", "").strip()
        body = canonical_version_text(version).strip()
        if page_title and page_title == body:
            blockers.append(f"{label}录入内容仅等于网页标题，不能当作规则原文。")
        if source.get("conflict_note"):
            warnings.append(f"{label}登记了来源冲突，应由律师逐项核实。")

        if data["mode"] == "production":
            if source["source_tier"] == "training_fixture" or version["text_basis"] == "training_fixture":
                blockers.append(f"{label}使用了教学测试来源，不得用于生产比对。")
            if source["source_tier"] == "other_traceable":
                blockers.append(f"{label}仅有其他可追溯来源，尚未补齐官方原文。")
        else:
            if source["source_tier"] != "training_fixture" or version["text_basis"] != "training_fixture":
                fatal.append("教学模式的新旧版本必须同时标记 training_fixture。")

    if new_version["effect_status"] == "unknown":
        blockers.append("新版本效力状态不明。")
    if new_version["effect_status"] == "not_yet_effective" and not new_version["effective_from"]:
        blockers.append("新版本尚未施行且缺少施行日期。")

    old_ids = {unit["unit_id"] for unit in old_version["units"]}
    new_ids = {unit["unit_id"] for unit in new_version["units"]}
    known_ids = old_ids | new_ids
    for index, mapping in enumerate(data.get("unit_mappings", [])):
        missing_old = set(mapping["old_unit_ids"]) - old_ids
        missing_new = set(mapping["new_unit_ids"]) - new_ids
        if missing_old or missing_new:
            fatal.append(
                f"unit_mappings[{index}] 引用了不存在的单元："
                f"old={sorted(missing_old)}, new={sorted(missing_new)}"
            )

    artifact_ids = [artifact["artifact_id"] for artifact in data["monitored_artifacts"]]
    duplicates = _duplicate_values(artifact_ids)
    if duplicates:
        fatal.append(f"受监测对象存在重复 artifact_id：{', '.join(duplicates)}")
    artifact_id_set = set(artifact_ids)
    for artifact in data["monitored_artifacts"]:
        missing = set(artifact["uses_unit_ids"]) - known_ids
        if missing:
            warnings.append(
                f"对象 {artifact['artifact_id']} 依赖未出现在新旧版本中的单元：{', '.join(sorted(missing))}。"
            )
    for index, claim in enumerate(data.get("impact_claims", [])):
        if claim["artifact_id"] not in artifact_id_set:
            fatal.append(f"impact_claims[{index}] 引用未登记 artifact_id。")
        if claim["unit_id"] not in known_ids:
            fatal.append(f"impact_claims[{index}] 引用未登记 unit_id。")

    return sorted(set(fatal)), sorted(set(blockers)), sorted(set(warnings))


def _change_id(analysis_id: str, change_type: str, unit_key: str) -> str:
    digest = hashlib.sha256(f"{analysis_id}\0{change_type}\0{unit_key}".encode("utf-8")).hexdigest()[:16]
    return f"chg-{digest}"


def _diff_ops(old_text: str, new_text: str) -> list[dict[str, Any]]:
    matcher = difflib.SequenceMatcher(a=old_text, b=new_text, autojunk=False)
    result: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        result.append(
            {
                "operation": tag,
                "old_span": [i1, i2],
                "new_span": [j1, j2],
                "old_text": old_text[i1:i2],
                "new_text": new_text[j1:j2],
            }
        )
    return result


def compare_versions(data: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    analysis_id = data["analysis_id"]
    old_units = {unit["unit_id"]: unit for unit in data["old_version"]["units"]}
    new_units = {unit["unit_id"]: unit for unit in data["new_version"]["units"]}
    mappings_by_id: dict[str, list[dict[str, Any]]] = {}
    for mapping in data.get("unit_mappings", []):
        for unit_id in set(mapping["old_unit_ids"] + mapping["new_unit_ids"]):
            mappings_by_id.setdefault(unit_id, []).append(mapping)

    changes: list[dict[str, Any]] = []
    unchanged_count = 0
    for unit_id in sorted(old_units.keys() | new_units.keys()):
        old_unit = old_units.get(unit_id)
        new_unit = new_units.get(unit_id)
        if old_unit is None:
            change_type = "added"
        elif new_unit is None:
            change_type = "removed"
        elif old_unit["text"] == new_unit["text"]:
            unchanged_count += 1
            continue
        else:
            change_type = "modified"

        old_text = old_unit["text"] if old_unit else ""
        new_text = new_unit["text"] if new_unit else ""
        categories = sorted(
            set((old_unit or {}).get("proposed_change_categories", []))
            | set((new_unit or {}).get("proposed_change_categories", []))
        )
        changes.append(
            {
                "change_id": _change_id(analysis_id, change_type, unit_id),
                "change_type": change_type,
                "unit_id": unit_id,
                "old_locator": old_unit.get("locator") if old_unit else None,
                "new_locator": new_unit.get("locator") if new_unit else None,
                "old_text": old_text or None,
                "new_text": new_text or None,
                "diff_operations": _diff_ops(old_text, new_text),
                "proposed_change_categories": categories,
                "category_status": "pending_human_review" if categories else "not_classified",
                "unit_mappings": mappings_by_id.get(unit_id, []),
            }
        )
    return changes, unchanged_count


def analyze_impacts(data: dict[str, Any], changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changed_ids = {change["unit_id"] for change in changes}
    change_text_by_id = {
        change["unit_id"]: f"{change.get('old_text') or ''}\n{change.get('new_text') or ''}".casefold()
        for change in changes
    }
    claims_by_artifact: dict[str, list[dict[str, Any]]] = {}
    for claim in data.get("impact_claims", []):
        claims_by_artifact.setdefault(claim["artifact_id"], []).append(claim)

    affected: list[dict[str, Any]] = []
    for artifact in sorted(data["monitored_artifacts"], key=lambda item: item["artifact_id"]):
        evidence: list[dict[str, Any]] = []
        for unit_id in sorted(set(artifact["uses_unit_ids"]) & changed_ids):
            evidence.append({"method": "unit_dependency", "unit_id": unit_id})
        for term in sorted(artifact["uses_terms"]):
            for unit_id in sorted(changed_ids):
                if term.casefold() in change_text_by_id[unit_id]:
                    evidence.append({"method": "term_match", "unit_id": unit_id, "term": term})
        claims = sorted(
            claims_by_artifact.get(artifact["artifact_id"], []),
            key=lambda item: (item["unit_id"], item["reason"]),
        )
        for claim in claims:
            if claim["unit_id"] in changed_ids:
                evidence.append(
                    {
                        "method": "analyst_claim",
                        "unit_id": claim["unit_id"],
                        "reason": claim["reason"],
                        "review_status": claim["review_status"],
                    }
                )
        if not evidence:
            continue
        confirmed_levels = [
            claim["impact_level"]
            for claim in claims
            if claim["unit_id"] in changed_ids and claim["review_status"] == "confirmed"
        ]
        level = max(confirmed_levels, key=IMPACT_ORDER.get) if confirmed_levels else "unknown"
        affected.append(
            {
                "artifact_id": artifact["artifact_id"],
                "artifact_type": artifact["artifact_type"],
                "name": artifact["name"],
                "skill_name": artifact.get("skill_name"),
                "path_label": artifact.get("path_label"),
                "production": artifact["production"],
                "impact_level": level,
                "impact_status": "human_confirmed" if confirmed_levels else "pending_human_review",
                "evidence": evidence,
                "claims": claims,
            }
        )
    return affected


def determine_gate(
    data: dict[str, Any],
    blockers: list[str],
    changes: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    if data["mode"] == "training_fixture":
        return "training_only", ["教学示例不得用于真实案件或生产更新。"]
    if blockers:
        return "blocked", blockers

    review = data.get("review_record")
    if not changes:
        return "pending_no_change_confirmation", ["未发现文本差异，仍需人工确认版本和效力。"]
    if not review or review["decision"] == "needs_more_information":
        return "pending_human_review", ["尚未完成执业律师人工复核。"]
    if review["decision"] == "rejected":
        return "review_rejected", ["人工复核未通过。"]

    checklist_missing = [key for key, value in review["checklist"].items() if not value]
    pending_claims = [
        claim for claim in data.get("impact_claims", []) if claim["review_status"] == "pending"
    ]
    if checklist_missing or pending_claims:
        reasons: list[str] = []
        if checklist_missing:
            reasons.append("人工复核清单未全部通过：" + "、".join(checklist_missing) + "。")
        if pending_claims:
            reasons.append("尚有未复核的影响主张。")
        return "pending_human_review", reasons
    return "approved_for_manual_update", ["仅允许在独立任务中人工更新；本报告未修改生产文件。"]


def build_report(data: dict[str, Any]) -> dict[str, Any]:
    fatal, blockers, warnings = gate_checks(data)
    if fatal:
        raise InputError("输入结构无效：\n- " + "\n- ".join(fatal))

    changes, unchanged_count = compare_versions(data)
    affected = analyze_impacts(data, changes)
    gate_status, gate_reasons = determine_gate(data, blockers, changes)
    impacted_skills = sorted(
        {item["skill_name"] for item in affected if item.get("skill_name")}
        | {item["name"] for item in affected if item["artifact_type"] == "skill"}
    )
    impacted_templates = sorted(
        item["artifact_id"] for item in affected if item["artifact_type"] == "template"
    )
    impacted_conclusions = sorted(
        item["artifact_id"] for item in affected if item["artifact_type"] == "prior_conclusion"
    )
    old_version = data["old_version"]
    new_version = data["new_version"]
    report = {
        "report_version": "1.0",
        "analysis_id": data["analysis_id"],
        "mode": data["mode"],
        "title": data["title"],
        "subject_type": data["subject_type"],
        "jurisdiction": data["jurisdiction"],
        "comparison_date": data["comparison_date"],
        "versions": {
            "old": {
                "version_id": old_version["version_id"],
                "title": old_version["title"],
                "effect_status": old_version["effect_status"],
                "verified_on": old_version["verified_on"],
                "effective_from": old_version["effective_from"],
                "text_sha256": old_version["text_sha256"],
                "source": old_version["source"],
            },
            "new": {
                "version_id": new_version["version_id"],
                "title": new_version["title"],
                "effect_status": new_version["effect_status"],
                "verified_on": new_version["verified_on"],
                "effective_from": new_version["effective_from"],
                "text_sha256": new_version["text_sha256"],
                "source": new_version["source"],
            },
        },
        "summary": {
            "change_count": len(changes),
            "added": sum(item["change_type"] == "added" for item in changes),
            "removed": sum(item["change_type"] == "removed" for item in changes),
            "modified": sum(item["change_type"] == "modified" for item in changes),
            "unchanged": unchanged_count,
            "affected_artifact_count": len(affected),
        },
        "changes": changes,
        "affected_artifacts": affected,
        "impacted_skills": impacted_skills,
        "impacted_templates": impacted_templates,
        "impacted_prior_conclusions": impacted_conclusions,
        "source_blockers": blockers,
        "warnings": warnings,
        "review_record": data.get("review_record"),
        "gate": {
            "status": gate_status,
            "reasons": gate_reasons,
            "production_files_modified": False,
            "automatic_production_update_allowed": False,
        },
    }
    errors = report_schema_errors(report)
    if errors:
        raise RuntimeError("内部报告契约校验失败：\n- " + "\n- ".join(errors))
    return report


def _md(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {_md(report['title'])}变更报告",
        "",
        "> AI 生成内容仅供学习参考，不得直接用于提交法院或对方当事人；最终结论须由执业律师逐项复核。",
        "",
        "## 门禁结果",
        "",
        f"- 状态：`{report['gate']['status']}`",
        "- 生产文件已修改：否",
        "- 允许自动更新生产文件：否",
    ]
    for reason in report["gate"]["reasons"]:
        lines.append(f"- 门禁说明：{reason}")

    old = report["versions"]["old"]
    new = report["versions"]["new"]
    lines += [
        "",
        "## 版本和来源",
        "",
        "| 版本 | 标题 | 效力 | 施行日 | 核验日 | 来源 | SHA-256 |",
        "|---|---|---|---|---|---|---|",
        f"| 旧版本 | {_md(old['title'])} | {_md(old['effect_status'])} | {_md(old['effective_from'])} | {_md(old['verified_on'])} | {_md(old['source']['url'])} | `{old['text_sha256']}` |",
        f"| 新版本 | {_md(new['title'])} | {_md(new['effect_status'])} | {_md(new['effective_from'])} | {_md(new['verified_on'])} | {_md(new['source']['url'])} | `{new['text_sha256']}` |",
        "",
        "## 变更摘要",
        "",
        f"- 新增：{report['summary']['added']} 项",
        f"- 删除：{report['summary']['removed']} 项",
        f"- 修改：{report['summary']['modified']} 项",
        f"- 未变：{report['summary']['unchanged']} 项",
        "",
        "## 变更记录",
        "",
        "| ID | 类型 | 单元 | 旧定位 | 新定位 | 建议分类 |",
        "|---|---|---|---|---|---|",
    ]
    if report["changes"]:
        for change in report["changes"]:
            categories = "、".join(change["proposed_change_categories"]) or "待分类"
            lines.append(
                f"| `{change['change_id']}` | {change['change_type']} | {_md(change['unit_id'])} | "
                f"{_md(change['old_locator'])} | {_md(change['new_locator'])} | {_md(categories)} |"
            )
    else:
        lines.append("| — | 未发现文本差异 | — | — | — | — |")

    lines += [
        "",
        "## 受影响对象",
        "",
        "| 对象 ID | 类型 | 名称 | Skill | 影响等级 | 状态 | 命中依据 |",
        "|---|---|---|---|---|---|---|",
    ]
    if report["affected_artifacts"]:
        for artifact in report["affected_artifacts"]:
            evidence = "；".join(
                f"{item['method']}:{item['unit_id']}" + (f":{item['term']}" if item.get("term") else "")
                for item in artifact["evidence"]
            )
            lines.append(
                f"| {_md(artifact['artifact_id'])} | {_md(artifact['artifact_type'])} | {_md(artifact['name'])} | "
                f"{_md(artifact.get('skill_name'))} | {_md(artifact['impact_level'])} | {_md(artifact['impact_status'])} | {_md(evidence)} |"
            )
    else:
        lines.append("| — | — | 未命中受监测对象 | — | — | — | — |")

    lines += [
        "",
        "### 受影响 Skill",
        "",
        *([f"- `{item}`" for item in report["impacted_skills"]] or ["- 无。"]),
        "",
        "### 受影响模板",
        "",
        *([f"- `{item}`" for item in report["impacted_templates"]] or ["- 无。"]),
        "",
        "### 受影响旧结论",
        "",
        *([f"- `{item}`" for item in report["impacted_prior_conclusions"]] or ["- 无。"]),
    ]

    if report["source_blockers"] or report["warnings"]:
        lines += ["", "## 问题与警告", ""]
        lines.extend(f"- 阻断：{item}" for item in report["source_blockers"])
        lines.extend(f"- 警告：{item}" for item in report["warnings"])

    lines += [
        "",
        "## 人工复核",
        "",
    ]
    review = report.get("review_record")
    if review:
        lines += [
            f"- 复核人：{_md(review['reviewer'])}",
            f"- 复核角色：{_md(review['reviewer_role'])}",
            f"- 复核时间：{_md(review['reviewed_at'])}",
            f"- 决定：`{review['decision']}`",
        ]
    else:
        lines.append("- 尚未提供人工复核记录。")
    lines += [
        "",
        "## 对外使用提示",
        "",
        "1. AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。",
        "2. 使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。",
        "3. AI 不能替代律师对案件具体情况进行独立法律判断。",
        "4. 本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。",
        "5. AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。",
        "",
        "本报告不会也不得自动修改生产模板。",
        "",
    ]
    return "\n".join(lines)


def atomic_write_report(report: dict[str, Any], output_value: str | Path) -> Path:
    output = Path(output_value).expanduser()
    if output.exists() or output.is_symlink():
        raise InputError(f"输出目录已存在，拒绝覆盖：{output}")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink():
        raise InputError("输出父目录不得是符号链接。")
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=parent))
    try:
        json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        md_text = report_markdown(report)
        (temp_dir / "change-report.json").write_text(json_text, encoding="utf-8", newline="\n")
        (temp_dir / "change-report.md").write_text(md_text, encoding="utf-8", newline="\n")
        os.replace(temp_dir, output)
    except Exception:
        if temp_dir.exists():
            for child in temp_dir.iterdir():
                child.unlink()
            temp_dir.rmdir()
        raise
    return output
