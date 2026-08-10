#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROUTES = {
    "property_preservation": ["申请对象和范围是否已经具体化", "财产线索及其来源是否可回查", "紧急性理由是否有材料支持", "担保要求是否经现行规则和受理机构核验"],
    "evidence_preservation": ["证据对象、所在位置和持有主体是否明确", "灭失或以后难以取得的风险是否有来源", "建议保全方式是否由律师确认"],
    "investigation_order": ["待调取材料及持有主体是否明确", "材料与争点的关系是否已登记", "自行获取障碍及已尝试措施是否有来源"],
    "appraisal": ["鉴定事项和鉴定问题是否由律师确认", "鉴定必要性是否指向已登记争点", "检材清单、来源和完整性是否待核对"],
    "extension": ["原定节点及其来源是否已核验", "无法按期完成的客观障碍是否有材料", "申请范围与备选安排是否由律师确认"],
    "suspension": ["拟主张的中止事由是否有来源", "事由与当前程序的关系是否经律师复核", "恢复程序的可能触发事件是否列入跟踪"],
    "recusal": ["申请对象是否特定", "回避事实是否按原文来源分项登记", "法律依据和程序节点是否已核验"],
    "other": ["申请名称和类型选择是否由律师确认", "请求、事实和受理主体是否已分别登记", "适用规则是否已通过法律检索核验"],
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(value: dict[str, Any], root: Path) -> list[str]:
    schema = _load(root / "schemas" / "application-input.schema.json")
    errors = [error.message for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)]
    source_ids = [item.get("source_id") for item in value.get("sources", [])]
    if len(source_ids) != len(set(source_ids)):
        errors.append("来源编号重复")
    registered_sources = set(source_ids)
    for statement in value.get("requested_relief", []) + value.get("supporting_facts", []) + value.get("urgency", {}).get("reasons", []):
        basis = statement.get("basis", {})
        if basis.get("basis_type") == "source_span" and basis.get("source_id") not in registered_sources:
            errors.append(f"请求或事实引用不存在来源：{basis.get('source_id')}")
    for material in value.get("materials", []):
        source_id = material.get("source_id")
        if source_id is not None and source_id not in registered_sources:
            errors.append(f"材料引用不存在来源：{source_id}")
    authority_ids = {item.get("authority_id") for item in value.get("authorities", [])}
    for field in ("deadline_review", "security_review"):
        review = value.get(field, {})
        if review.get("status") == "unverified" and (review.get("conclusion") is not None or review.get("authority_ids")):
            errors.append(f"{field} 未核验时不得登记结论或法源")
        if review.get("status") == "verified":
            if not review.get("conclusion") or not review.get("authority_ids"):
                errors.append(f"{field} 标记已核验时必须登记结论和法源")
            missing = set(review.get("authority_ids", [])) - authority_ids
            if missing:
                errors.append(f"{field} 引用不存在法源：{sorted(missing)}")
    if value.get("external_action_requested"):
        errors.append("禁止自动签名、盖章、发送或提交程序申请")
    return sorted(errors)


def derive(value: dict[str, Any]) -> dict[str, Any]:
    checklist = [{"item_id": f"ROUTE-{index:02d}", "question": text, "status": "lawyer_review_required"} for index, text in enumerate(ROUTES[value["application_type"]], 1)]
    gaps = [{"material_id": item["material_id"], "name": item["name"], "status": item["status"]} for item in value["materials"] if item["status"] != "available"]
    reviews: list[dict[str, str]] = []
    for field, label in (("deadline_review", "期限"), ("security_review", "担保")):
        if value[field]["status"] != "verified":
            reviews.append({"review_id": field, "question": f"核验{label}要求、适用时点及受理机构最新规则", "status": "lawyer_review_required"})
    if value["application_type"] == "other":
        reviews.append({"review_id": "application_type", "question": "由律师确认申请类型及对应程序规则", "status": "lawyer_review_required"})
    return {
        "schema_version": "1.0", "matter_id": value["matter_id"], "application_id": value["application_id"],
        "application_type": value["application_type"], "artifact_state": "lawyer_review_required",
        "routing_checklist": checklist, "material_gaps": gaps, "review_items": reviews, "source_record": value,
    }


def markdown(result: dict[str, Any]) -> str:
    source = result["source_record"]
    lines = ["# 程序申请工作底稿", "", f"案件编号：{result['matter_id']}  ", f"申请编号：{result['application_id']}  ", f"申请类型：{result['application_type']}  ", "状态：待律师复核", "", "## 一、申请请求"]
    lines += [f"- {item['statement_id']}：{item['text']}（来源：{item['basis']['basis_type']}）" for item in source["requested_relief"]]
    lines += ["", "## 二、支撑事实"]
    lines += [f"- {item['statement_id']}：{item['text']}（来源：{item['basis']['basis_type']}）" for item in source["supporting_facts"]]
    lines += ["", "## 三、路由核对清单"]
    lines += [f"- [ ] {item['question']}" for item in result["routing_checklist"]]
    lines += ["", "## 四、材料缺口"]
    lines += [f"- {item['material_id']}：{item['name']}（{item['status']}）" for item in result["material_gaps"]] or ["- 未标记材料缺口，仍须律师核对。"]
    lines += ["", "## 五、待律师复核"]
    lines += [f"- [ ] {item['question']}" for item in result["review_items"]] or ["- 仍须律师对全部事实、证据和法律适用作最终复核。"]
    lines += ["", "本底稿不是可直接提交的申请书，不含自动签章或提交功能。", ""]
    return "\n".join(lines)


def build(input_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    root = Path(__file__).resolve().parent.parent
    value = _load(input_path)
    errors = validate(value, root)
    if errors:
        raise ValueError("；".join(errors))
    result = derive(value)
    out_schema = _load(root / "schemas" / "application-output.schema.json")
    Draft202012Validator(out_schema).validate(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (temp / "application-workpaper.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "程序申请工作底稿.md").write_text(markdown(result), encoding="utf-8")
        temp.replace(output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="生成待律师复核的程序申请工作底稿")
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
