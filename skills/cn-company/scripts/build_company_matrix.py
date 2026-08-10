#!/usr/bin/env python3
"""Build a deterministic company-governance review matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SKILL_DIR = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = SKILL_DIR / "schemas" / "company-input.schema.json"
OUTPUT_SCHEMA = SKILL_DIR / "schemas" / "company-output.schema.json"

STAGES = (
    ("authority_review", "权限依据复核"),
    ("convocation", "召集程序复核"),
    ("notice", "通知程序复核"),
    ("voting", "表决及回避复核"),
    ("minutes", "会议记录或书面决议底稿复核"),
    ("signing", "签署权限和签署版本复核"),
    ("registration_disclosure", "登记与披露必要性复核"),
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(instance: Any, schema_path: Path) -> None:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance),
        key=lambda err: list(err.absolute_path),
    )
    if errors:
        details = "; ".join(f"{'/'.join(map(str, err.absolute_path)) or '<root>'}: {err.message}" for err in errors)
        raise ValueError(f"Schema validation failed: {details}")


def build_matrix(data: dict[str, Any]) -> dict[str, Any]:
    source_ids = {item["source_id"] for item in data["authority_sources"]}
    charter_ids = {item["charter_id"] for item in data["charter_versions"]}
    current_ids = sorted(item["charter_id"] for item in data["charter_versions"] if item["status"] == "confirmed_current")
    charter_blockers: list[str] = []
    if len(current_ids) == 0:
        charter_blockers.append("未确认唯一现行章程版本。")
    elif len(current_ids) > 1:
        charter_blockers.append("存在多个标记为现行的章程版本，须人工消除冲突。")
    missing_charter_sources = sorted({item["source_id"] for item in data["charter_versions"]} - source_ids)
    if missing_charter_sources:
        charter_blockers.append(f"章程来源不存在：{', '.join(missing_charter_sources)}。")

    global_blockers = list(charter_blockers)
    warnings: list[str] = []
    if data["company"]["company_type"] == "other":
        warnings.append("公司类型为 other，须补充特殊组织或行业规则。")
    if not data["shareholders"]:
        warnings.append("股东名册为空。")
    if not data["governance_persons"]:
        warnings.append("董监高或治理人员名册为空。")
    if any(item["verification_status"] != "verified" for item in data["shareholders"]):
        warnings.append("股东名册存在未核验或冲突记录。")
    if any(item["appointment_status"] != "verified" for item in data["governance_persons"]):
        warnings.append("治理人员名册存在未核验或冲突记录。")

    agendas: dict[str, dict[str, Any]] = {}
    agenda_map: list[dict[str, Any]] = []
    for agenda in data["agenda_items"]:
        blockers: list[str] = []
        if not agenda["authority_source_ids"]:
            blockers.append("议题未登记权限依据。")
        missing_sources = sorted(set(agenda["authority_source_ids"]) - source_ids)
        missing_charters = sorted(set(agenda["charter_ids"]) - charter_ids)
        if missing_sources:
            blockers.append(f"权限来源不存在：{', '.join(missing_sources)}。")
        if missing_charters:
            blockers.append(f"章程版本不存在：{', '.join(missing_charters)}。")
        if current_ids and current_ids[0] not in agenda["charter_ids"]:
            blockers.append("议题未绑定已确认的现行章程。")
        record = {
            "agenda_id": agenda["agenda_id"],
            "title": agenda["title"],
            "proposed_body": agenda["proposed_body"],
            "authority_source_ids": sorted(agenda["authority_source_ids"]),
            "charter_ids": sorted(agenda["charter_ids"]),
            "status": "blocked" if blockers else "pending_lawyer_review",
            "blockers": blockers,
        }
        agendas[agenda["agenda_id"]] = record
        agenda_map.append(record)
        global_blockers.extend(f"议题 {agenda['agenda_id']}：{item}" for item in blockers)

    tasks: list[dict[str, Any]] = []
    for action in data["governance_actions"]:
        action_blockers: list[str] = []
        missing_agendas = sorted(set(action["agenda_ids"]) - set(agendas))
        if not action["agenda_ids"]:
            action_blockers.append("行动未关联议题。")
        if missing_agendas:
            action_blockers.append(f"关联议题不存在：{', '.join(missing_agendas)}。")
        missing_rules = sorted(set(action["rule_source_ids"]) - source_ids)
        if not action["rule_source_ids"]:
            action_blockers.append("行动未登记程序规则来源。")
        if missing_rules:
            action_blockers.append(f"程序规则来源不存在：{', '.join(missing_rules)}。")
        if not action["notice_rule_text"].strip():
            action_blockers.append("通知规则尚未输入。")
        if not action["voting_rule_text"].strip():
            action_blockers.append("表决规则尚未输入。")
        linked_agenda_blockers = [
            blocker
            for agenda_id in action["agenda_ids"]
            if agenda_id in agendas
            for blocker in agendas[agenda_id]["blockers"]
        ]
        action_blockers.extend(linked_agenda_blockers)

        for index, (stage, label) in enumerate(STAGES, start=1):
            blockers = list(action_blockers)
            responsible = action["responsible_by_stage"].get(stage, "")
            if not responsible.strip():
                blockers.append("未指定阶段责任人。")
            if stage == "convocation" and not action["convenor"].strip():
                blockers.append("未输入召集人。")
            if stage == "signing" and not action["signing_responsible"].strip():
                blockers.append("未输入签署责任人；脚本不会代签。")
            if stage == "registration_disclosure":
                if action["registration_need"] == "to_be_determined":
                    blockers.append("登记必要性待律师判断。")
                if action["disclosure_need"] == "to_be_determined":
                    blockers.append("披露必要性待律师判断。")
            tasks.append(
                {
                    "task_id": f"{action['action_id']}-{index:02d}",
                    "action_id": action["action_id"],
                    "stage": stage,
                    "label": label,
                    "responsible": responsible,
                    "agenda_ids": sorted(action["agenda_ids"]),
                    "rule_source_ids": sorted(action["rule_source_ids"]),
                    "registration_need": action["registration_need"] if stage == "registration_disclosure" else None,
                    "disclosure_need": action["disclosure_need"] if stage == "registration_disclosure" else None,
                    "status": "blocked" if blockers else "pending_lawyer_review",
                    "blockers": sorted(set(blockers)),
                    "completion_evidence": "由律师登记实际通知、签到、表决、签署或办理材料；脚本不代为完成。",
                }
            )
        global_blockers.extend(f"行动 {action['action_id']}：{item}" for item in action_blockers)

    result = {
        "schema_version": "1.0",
        "matter_id": data["matter_id"],
        "as_of_date": data["as_of_date"],
        "input_sha256": hashlib.sha256(canonical_bytes(data)).hexdigest(),
        "company_snapshot": data["company"],
        "authority_register": data["authority_sources"],
        "charter_versions": data["charter_versions"],
        "shareholder_register": data["shareholders"],
        "governance_person_register": data["governance_persons"],
        "charter_gate": {
            "status": "blocked" if charter_blockers else "ready_for_lawyer_review",
            "confirmed_current_ids": current_ids,
            "blockers": charter_blockers,
        },
        "agenda_authority_map": agenda_map,
        "task_matrix": tasks,
        "global_blockers": sorted(set(global_blockers)),
        "warnings": sorted(set(warnings)),
        "resolution_validity_determined": False,
        "external_submission_performed": False,
        "artifact_state": "lawyer_review_required",
    }
    validate(result, OUTPUT_SCHEMA)
    return result


def render_markdown(result: dict[str, Any]) -> str:
    rows = []
    for task in result["task_matrix"]:
        rows.append(
            f"| {task['task_id']} | {task['label']} | {task['responsible'] or '未指定'} | "
            f"{task['status']} | {'；'.join(task['blockers']) or '无结构化阻断项'} |"
        )
    blockers = "\n".join(f"- {item}" for item in result["global_blockers"]) or "- 无结构化阻断项，但仍须律师复核。"
    warnings = "\n".join(f"- {item}" for item in result["warnings"]) or "- 无。"
    return f"""# 公司治理任务矩阵（律师复核底稿）

- 事项编号：{result['matter_id']}
- 核验时点：{result['as_of_date']}
- 公司：{result['company_snapshot']['name']}
- 固定状态：`lawyer_review_required`
- 决议有效性：未判断
- 外部提交：未执行

## 任务矩阵

| 任务 | 阶段 | 责任人 | 状态 | 阻断项 |
|---|---|---|---|---|
{os.linesep.join(rows)}

## 全局阻断项

{blockers}

## 告警

{warnings}

本底稿不认定决议有效，不生成签名或印章，不办理登记或披露。所有事实、权限、程序、期限与材料须由执业律师逐项复核。
"""


def write_atomic(result: dict[str, Any], output_dir: Path) -> None:
    if output_dir.exists():
        raise FileExistsError(f"Output directory already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        (temp_dir / "company-matrix.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (temp_dir / "company-matrix.md").write_text(render_markdown(result), encoding="utf-8")
        temp_dir.rename(output_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = load_json(args.input)
    validate(data, INPUT_SCHEMA)
    result = build_matrix(data)
    write_atomic(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
