#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


CONTROL_LABELS = {
    "conflict_check": "利益冲突检查",
    "identity_verification": "身份与权限核验",
    "deadline_review": "期限风险审查",
    "emergency_measure_review": "紧急措施审查",
    "engagement_review": "委托承办审查",
}


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
    schema = json.loads((skill_root / "schemas" / "intake.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"Schema {'.'.join(str(part) for part in error.path) or '<root>'}：{error.message}"
        for error in validator.iter_errors(value)
    ]


def duplicated(items: list[dict[str, Any]], key: str) -> list[str]:
    values = [str(item.get(key, "")) for item in items]
    return sorted({value for value in values if value and values.count(value) > 1})


def validate(value: dict[str, Any], skill_root: Path) -> dict[str, Any]:
    errors = schema_errors(value, skill_root)
    warnings: list[str] = []
    materials = value.get("materials", [])
    participants = value.get("participants", [])
    statements = value.get("statements", [])
    source_ids = {item.get("source_id") for item in materials}

    for items, key, label in (
        (participants, "party_id", "参与人编号"),
        (materials, "source_id", "材料编号"),
        (statements, "statement_id", "陈述编号"),
    ):
        duplicate_values = duplicated(items, key)
        if duplicate_values:
            errors.append(f"{label}重复：{'、'.join(duplicate_values)}")

    hashes = [item.get("sha256") for item in materials]
    if len(hashes) != len(set(hashes)):
        warnings.append("存在 SHA-256 相同的材料，应核对是否为重复文件")

    for statement in statements:
        sid = statement.get("statement_id", "未知陈述")
        spans = statement.get("source_spans", [])
        for span in spans:
            if span.get("source_id") not in source_ids:
                errors.append(f"{sid} 引用了不存在的材料：{span.get('source_id')}")
        if statement.get("status") == "user_confirmed" and not spans and not statement.get("confirmation_note"):
            errors.append(f"{sid} 标为 user_confirmed，但没有来源或确认说明")
        if statement.get("status") == "derived" and not statement.get("derivation_rule"):
            errors.append(f"{sid} 标为 derived，但没有推导规则")

    for participant in participants:
        if participant.get("name_status") == "user_confirmed" and not participant.get("source_spans") and not participant.get("confirmation_note"):
            errors.append(f"{participant.get('party_id')} 的名称已确认，但没有来源或确认说明")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def analyze(value: dict[str, Any]) -> dict[str, Any]:
    missing_by_field: dict[str, dict[str, str]] = {}
    blockers: list[dict[str, str]] = []
    questions: list[str] = []

    def add_missing(field: str, reason: str) -> None:
        current = missing_by_field.get(field)
        if current is None:
            missing_by_field[field] = {"field": field, "reason": reason}
        elif reason not in current["reason"].split("；"):
            current["reason"] += f"；{reason}"

    if not value["participants"]:
        add_missing("participants", "尚未记录任何相关参与人")
        questions.append("请分别说明委托人、对方及其他相关主体的身份和相互关系。")
    if not value["materials"]:
        add_missing("materials", "尚未登记任何材料")
        questions.append("目前持有哪些合同、通知、付款凭证、沟通记录或程序文书？")
    if not value["request"]["desired_outcomes"]:
        add_missing("request.desired_outcomes", "尚未确认委托人的目标")
        questions.append("希望律师最终协助实现哪些具体结果？请区分优先目标和可接受方案。")

    for statement in value["statements"]:
        status = statement["status"]
        if status in {"missing", "conflict", "unreadable"}:
            add_missing(statement["field"], f"事实状态为 {status}")
            questions.append(f"请补充或核对“{statement['field']}”，并说明可以回查的材料位置。")

    for key, control in value["controls"].items():
        status = control["status"]
        label = CONTROL_LABELS[key]
        if status == "blocked":
            blockers.append({"control": key, "reason": f"{label}处于 blocked"})
        elif status in {"not_started", "pending"}:
            add_missing(f"controls.{key}", f"{label}尚未完成")
            questions.append(f"请由有权限人员完成{label}并记录结论。")

    if blockers:
        release_status = "blocked"
    elif missing_by_field:
        release_status = "needs_information"
    else:
        release_status = "ready_for_lawyer_decision"
    return {
        "schema_version": "1.0",
        "intake_id": value["intake_id"],
        "matter_id": value["matter"]["matter_id"],
        "release_status": release_status,
        "blockers": blockers,
        "missing_information": list(missing_by_field.values()),
        "interview_questions": list(dict.fromkeys(questions)),
    }


def summary_markdown(value: dict[str, Any], analysis: dict[str, Any]) -> str:
    lines = [
        "# 收案访谈整理稿",
        "",
        f"案件编号：{analysis['matter_id']}  ",
        f"收案记录：{analysis['intake_id']}  ",
        f"机器状态：{analysis['release_status']}",
        "",
        "## 一、委托人原始诉求",
        "",
        value["request"]["raw_request"],
        "",
        "## 二、期望结果",
        "",
    ]
    lines.extend(f"- {item}" for item in value["request"]["desired_outcomes"])
    lines.extend(["", "## 三、参与人", ""])
    for item in value["participants"]:
        lines.append(f"- {item['party_id']}：{item.get('name', '待确认')}｜{'、'.join(item['procedural_roles'])}｜{item['name_status']}")
    lines.extend(["", "## 四、材料", ""])
    for item in value["materials"]:
        lines.append(f"- {item['source_id']}：{item['file_name']}｜{item['parse_status']}｜SHA-256 {item['sha256']}")
    lines.extend(["", "## 五、缺失事项与阻断项", ""])
    for item in analysis["blockers"]:
        lines.append(f"- 阻断：{item['reason']}")
    for item in analysis["missing_information"]:
        lines.append(f"- 待补：{item['field']}——{item['reason']}")
    if not analysis["blockers"] and not analysis["missing_information"]:
        lines.append("- 未发现机器可识别的缺失项；仍须律师独立审查。")
    lines.extend(["", "## 六、补充访谈问题", ""])
    lines.extend(f"{index}. {item}" for index, item in enumerate(analysis["interview_questions"], 1))
    lines.extend([
        "",
        "## 七、使用边界",
        "",
        "本整理稿不表示利益冲突已经通过、诉讼时效已经核验、案件已经承办或任何法律结论成立。",
    ])
    return "\n".join(lines) + "\n"


def build(input_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    value = load_json(input_path)
    skill_root = Path(__file__).resolve().parent.parent
    validation = validate(value, skill_root)
    if not validation["ok"]:
        raise ValueError("；".join(validation["errors"]))
    analysis = analyze(value)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-intake-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        (temp / "intake.normalized.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "intake-analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "收案访谈整理稿.md").write_text(summary_markdown(value, analysis), encoding="utf-8")
        temp.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="整理中国律师收案访谈数据、缺口和人工门禁")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.input, args.output)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] 已生成收案整理结果：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
