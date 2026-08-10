#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


AUDIO_VIDEO = re.compile(r"\.(?:mp3|m4a|wav|aac|flac|ogg|mp4|mov|mkv|webm)$", re.IGNORECASE)
HEARING_WORD = re.compile(r"庭审|开庭|法庭")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(value: dict[str, Any], root: Path) -> list[str]:
    schema = load(root / "schemas" / "hearing-input.schema.json")
    errors = [error.message for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)]
    if value.get("recording_action") != "none":
        errors.append("禁止对庭审录音进行转写、摘要或内容提取")
    for source in value.get("sources", []):
        file_name = source.get("file_name", "")
        mime = source.get("mime_type") or ""
        if source.get("kind") == "hearing_audio" or (HEARING_WORD.search(file_name) and (AUDIO_VIDEO.search(file_name) or mime.startswith(("audio/", "video/")))):
            errors.append(f"禁止处理庭审录音来源：{source.get('source_id', '未编号')}")
    if value.get("external_action_requested"):
        errors.append("禁止自动对外发送、提交证据或作出事实承认")

    matter_id = value.get("matter_id")
    if value.get("case_analysis", {}).get("matter_id") != matter_id:
        errors.append("cn-case-analysis 的 matter_id 与当前案件不一致")
    if value.get("evidence_map", {}).get("matter_id") != matter_id:
        errors.append("cn-evidence-map 的 matter_id 与当前案件不一致")

    issues = [item.get("issue_id") for item in value.get("case_analysis", {}).get("issues", [])]
    evidence = [item.get("evidence_id") for item in value.get("evidence_map", {}).get("evidence", [])]
    if len(issues) != len(set(issues)):
        errors.append("争点编号重复")
    if len(evidence) != len(set(evidence)):
        errors.append("证据编号重复")
    issue_ids, evidence_ids = set(issues), set(evidence)
    for link in value.get("evidence_map", {}).get("issue_links", []):
        if link.get("issue_id") not in issue_ids:
            errors.append(f"证据关联引用不存在争点：{link.get('issue_id')}")
        if link.get("evidence_id") not in evidence_ids:
            errors.append(f"证据关联引用不存在证据：{link.get('evidence_id')}")
    for group, label in ((value.get("question_plans", []), "提问"), (value.get("objection_plans", []), "异议")):
        for item in group:
            if item.get("issue_id") not in issue_ids:
                errors.append(f"{label}引用不存在争点：{item.get('issue_id')}")
            for evidence_id in item.get("evidence_ids", []):
                if evidence_id not in evidence_ids:
                    errors.append(f"{label}引用不存在证据：{evidence_id}")
    for task in value.get("post_hearing_tasks", []):
        for issue_id in task.get("issue_ids", []):
            if issue_id not in issue_ids:
                errors.append(f"庭后任务引用不存在争点：{issue_id}")
    return sorted(set(errors))


def derive(value: dict[str, Any]) -> dict[str, Any]:
    evidence_by_id = {item["evidence_id"]: item for item in value["evidence_map"]["evidence"]}
    links: dict[str, list[str]] = {}
    for link in value["evidence_map"]["issue_links"]:
        links.setdefault(link["issue_id"], []).append(link["evidence_id"])
    questions: dict[str, list[dict[str, Any]]] = {}
    for item in value["question_plans"]:
        questions.setdefault(item["issue_id"], []).append(item)
    objections: dict[str, list[dict[str, Any]]] = {}
    for item in value["objection_plans"]:
        objections.setdefault(item["issue_id"], []).append(item)
    tasks: dict[str, list[str]] = {}
    for item in value["post_hearing_tasks"]:
        for issue_id in item["issue_ids"]:
            tasks.setdefault(issue_id, []).append(item["task_id"])

    matrix, gaps = [], []
    for issue in sorted(value["case_analysis"]["issues"], key=lambda item: item["issue_id"]):
        issue_id = issue["issue_id"]
        evidence_items = [evidence_by_id[item] for item in sorted(set(links.get(issue_id, [])))]
        matrix.append({
            "issue": issue,
            "evidence": evidence_items,
            "question_plans": sorted(questions.get(issue_id, []), key=lambda item: item["question_id"]),
            "objection_plans": sorted(objections.get(issue_id, []), key=lambda item: item["objection_id"]),
            "post_hearing_task_ids": sorted(tasks.get(issue_id, [])),
            "status": "lawyer_review_required",
        })
        if not evidence_items:
            gaps.append({"gap_type": "issue_without_linked_evidence", "issue_id": issue_id})
        if not questions.get(issue_id):
            gaps.append({"gap_type": "issue_without_question_plan", "issue_id": issue_id})
        for evidence_item in evidence_items:
            if evidence_item["proof_purpose_status"] == "missing":
                gaps.append({"gap_type": "proof_purpose_missing", "issue_id": issue_id, "evidence_id": evidence_item["evidence_id"]})
            if "unreviewed" in {evidence_item["authenticity"], evidence_item["legality"], evidence_item["relevance"]}:
                gaps.append({"gap_type": "three_nature_review_incomplete", "issue_id": issue_id, "evidence_id": evidence_item["evidence_id"]})
    return {
        "schema_version": "1.0", "matter_id": value["matter_id"], "preparation_id": value["preparation_id"],
        "artifact_state": "lawyer_review_required", "admission_state": "no_admissions_made", "question_plan_state": "not_testimony_or_fact",
        "matrix": matrix, "gaps": sorted(gaps, key=lambda item: (item["issue_id"], item["gap_type"], item.get("evidence_id", ""))),
        "post_hearing_tasks": sorted(value["post_hearing_tasks"], key=lambda item: item["task_id"]),
    }


def markdown(result: dict[str, Any]) -> str:
    lines = ["# 庭前庭审准备矩阵", "", f"案件编号：{result['matter_id']}  ", f"准备编号：{result['preparation_id']}  ", "状态：待律师复核  ", "事实承认：本底稿未作出任何承认  ", "提问计划：不是证言或已确认事实", ""]
    for index, row in enumerate(result["matrix"], 1):
        issue = row["issue"]
        lines += [f"## {index}. {issue['issue_id']}：{issue['question']}", "", f"分析框架：{issue['frame']}；上游状态：{issue['status']}", "", "### 证据"]
        lines += [f"- {item['evidence_id']}：{item['name']}｜三性：{item['authenticity']}/{item['legality']}/{item['relevance']}｜证明目的：{item['proof_purpose_status']}" for item in row["evidence"]] or ["- 无关联证据，待律师核对。"]
        lines += ["", "### 提问计划（非证言）"]
        lines += [f"- [ ] {item['question_id']}：{item['text']}｜目的：{item['purpose']}" for item in row["question_plans"]] or ["- 未登记提问计划。"]
        lines += ["", "### 异议预案"]
        lines += [f"- [ ] {item['objection_id']}：触发情形——{item['trigger']}；工作回应——{item['working_response']}" for item in row["objection_plans"]] or ["- 未登记异议预案，不表示当庭无异议事项。"]
        lines += ["", "### 庭后任务指针", "- " + ("、".join(row["post_hearing_task_ids"]) if row["post_hearing_task_ids"] else "未关联任务。"), ""]
    lines += ["## 断链与待复核", ""]
    lines += [f"- {item['issue_id']}：{item['gap_type']}" + (f"（{item['evidence_id']}）" if item.get("evidence_id") else "") for item in result["gaps"]] or ["- 机械检查未发现断链，仍须出庭律师逐项复核。"]
    lines += ["", "## 庭后任务", ""]
    lines += [f"- [{item['status']}] {item['task_id']}：{item['description']}｜责任角色：{item['owner_role']}｜目标日期原文：{item['target_date_raw'] or '待确认'}" for item in result["post_hearing_tasks"]] or ["- 未登记庭后任务。"]
    lines += ["", "本底稿不处理庭审录音，不作事实承认，不代替出庭律师的当庭判断。", ""]
    return "\n".join(lines)


def build(input_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    root = Path(__file__).resolve().parent.parent
    value = load(input_path)
    errors = validate(value, root)
    if errors:
        raise ValueError("；".join(errors))
    result = derive(value)
    Draft202012Validator(load(root / "schemas" / "hearing-output.schema.json")).validate(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (temp / "hearing-workbook.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "庭前庭审准备矩阵.md").write_text(markdown(result), encoding="utf-8")
        temp.replace(output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="生成待律师复核的庭前庭审准备矩阵")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        build(args.input, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
