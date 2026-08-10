#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ids(items: Iterable[dict[str, Any]], key: str) -> list[str]:
    return [str(item.get(key)) for item in items]


def _duplicate_errors(items: Iterable[dict[str, Any]], key: str, label: str) -> list[str]:
    values = _ids(items, key)
    return [f"{label}编号重复"] if len(values) != len(set(values)) else []


def _citations(value: dict[str, Any]) -> Iterable[dict[str, Any]]:
    judgment = value.get("judgment", {})
    for group in ("operative_part", "reasoning", "issues"):
        for item in judgment.get(group, []):
            yield item.get("citation", {})
    for issue in value.get("review_issues", []):
        yield from issue.get("supporting_citations", [])
        yield from issue.get("opposing_citations", [])
    yield from (item.get("citation", {}) for item in value.get("deadline_review", {}).get("service_facts", []))
    yield from (item.get("citation", {}) for item in value.get("evidence", []))
    yield from (item.get("explanation_basis", {}) for item in value.get("new_evidence_explanations", []))


def validate(value: dict[str, Any], root: Path) -> list[str]:
    schema = _load(root / "schemas" / "appeal-input.schema.json")
    errors = [error.message for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)]
    errors += _duplicate_errors(value.get("sources", []), "source_id", "来源")
    errors += _duplicate_errors(value.get("authorities", []), "authority_id", "法源")
    errors += _duplicate_errors(value.get("appeal_requests", []), "request_id", "上诉请求")
    errors += _duplicate_errors(value.get("review_issues", []), "issue_id", "复核问题")
    errors += _duplicate_errors(value.get("evidence", []), "evidence_id", "证据")

    source_ids = set(_ids(value.get("sources", []), "source_id"))
    authority_ids = set(_ids(value.get("authorities", []), "authority_id"))
    if value.get("judgment", {}).get("source_id") not in source_ids:
        errors.append("原审裁判引用不存在来源")
    for citation in _citations(value):
        if citation.get("source_id") not in source_ids:
            errors.append(f"引用不存在来源：{citation.get('source_id')}")
    for request in value.get("appeal_requests", []):
        basis = request.get("basis", {})
        if basis.get("basis_type") == "source_span" and basis.get("source_id") not in source_ids:
            errors.append(f"上诉请求引用不存在来源：{basis.get('source_id')}")

    deadline = value.get("deadline_review", {})
    for rule in deadline.get("rule_inputs", []):
        if rule.get("authority_id") not in authority_ids:
            errors.append(f"期限规则引用不存在法源：{rule.get('authority_id')}")
    if deadline.get("status") == "unverified" and deadline.get("lawyer_conclusion") is not None:
        errors.append("期限未核验时不得登记律师结论")
    if deadline.get("status") == "verified_by_lawyer" and not deadline.get("rule_inputs"):
        errors.append("期限已核验时必须登记期限规则")

    evidence_ids = set(_ids(value.get("evidence", []), "evidence_id"))
    for explanation in value.get("new_evidence_explanations", []):
        if explanation.get("evidence_id") not in evidence_ids:
            errors.append(f"新证据说明引用不存在证据：{explanation.get('evidence_id')}")
        if explanation.get("claimed_as_new") and not explanation.get("not_submitted_reason"):
            errors.append(f"声称新证据时必须登记未在原审提交原因：{explanation.get('evidence_id')}")
    if value.get("external_action_requested"):
        errors.append("禁止自动签章或提交上诉材料")
    return sorted(set(errors))


def derive(value: dict[str, Any]) -> dict[str, Any]:
    issue_audit = {kind: [] for kind in ("fact_dispute", "legal_application", "procedural_issue")}
    for item in value["review_issues"]:
        issue_audit[item["issue_type"]].append(item)
    request_integrity = [
        {
            "request_id": item["request_id"],
            "verbatim_text": item["verbatim_text"],
            "text_sha256": hashlib.sha256(item["verbatim_text"].encode("utf-8")).hexdigest(),
            "status": "verbatim_preserved",
        }
        for item in value["appeal_requests"]
    ]
    deadline = value["deadline_review"]
    reviews = [
        {"item_id": "APPEAL-DEADLINE", "question": "由律师依期限规则、送达事实与日历规则判断是否逾期", "status": "lawyer_review_required"},
        {"item_id": "APPEAL-CAUSE", "question": "由律师确认案件类型、案由及对应程序", "status": "lawyer_review_required"},
        {"item_id": "APPEAL-REQUESTS", "question": "逐字核对上诉请求与当事人最终授权文本", "status": "lawyer_review_required"},
        {"item_id": "APPEAL-EVIDENCE", "question": "复核证据三性、证明目的及新证据程序说明", "status": "lawyer_review_required"},
    ]
    return {
        "schema_version": "1.0",
        "matter_id": value["matter_id"],
        "appeal_id": value["appeal_id"],
        "case_type": value["case_type"],
        "artifact_state": "lawyer_review_required",
        "request_integrity": request_integrity,
        "issue_audit": issue_audit,
        "deadline_audit": {
            "status": deadline["status"],
            "rule_inputs": deadline["rule_inputs"],
            "service_facts": deadline["service_facts"],
            "lawyer_conclusion": deadline["lawyer_conclusion"],
            "automatic_deadline_decision": None,
        },
        "evidence_audit": {"evidence": value["evidence"], "new_evidence_explanations": value["new_evidence_explanations"]},
        "review_items": reviews,
        "source_record": value,
    }


def markdown(result: dict[str, Any]) -> str:
    source = result["source_record"]
    lines = ["# 上诉审查工作底稿", "", f"案件编号：{result['matter_id']}  ", f"审查编号：{result['appeal_id']}  ", f"案件类型：{result['case_type']}  ", "状态：待执业律师复核", "", "## 一、原审裁判主文"]
    lines += [f"- {item['statement_id']}：{item['text']}（{item['citation']['source_id']} / {item['citation']['locator']}）" for item in source["judgment"]["operative_part"]]
    lines += ["", "## 二、原审说理与争点", "### 原审说理"]
    lines += [f"- {item['statement_id']}：{item['text']}" for item in source["judgment"]["reasoning"]] or ["- 未录入。"]
    lines += ["", "### 原审争点"]
    lines += [f"- {item['statement_id']}：{item['text']}" for item in source["judgment"]["issues"]] or ["- 未录入。"]
    lines += ["", "## 三、上诉请求（逐字保留）"]
    lines += [f"- {item['request_id']}：{item['verbatim_text']}  \n  SHA-256：`{item['text_sha256']}`" for item in result["request_integrity"]]
    labels = {"fact_dispute": "事实争议", "legal_application": "法律适用", "procedural_issue": "程序问题"}
    lines += ["", "## 四、分类复核问题"]
    for kind, label in labels.items():
        lines.append(f"### {label}")
        lines += [f"- {item['issue_id']}：{item['question']}" for item in result["issue_audit"][kind]] or ["- 未录入。"]
    lines += ["", "## 五、期限与送达审计", "- 自动期限结论：无，须由律师判断。"]
    lines += [f"- 送达事实：{item['text']}（{item['citation']['source_id']} / {item['citation']['locator']}）" for item in result["deadline_audit"]["service_facts"]] or ["- 未录入送达事实。"]
    lines += ["", "## 六、证据与新证据说明"]
    lines += [f"- {item['evidence_id']}：{item['name']}；证明目的：{item['purpose']}" for item in result["evidence_audit"]["evidence"]] or ["- 未录入证据。"]
    lines += [f"- 新证据说明 {item['evidence_id']}：{item['not_submitted_reason'] or '未填写'}" for item in result["evidence_audit"]["new_evidence_explanations"]]
    lines += ["", "## 七、待律师复核"]
    lines += [f"- [ ] {item['question']}" for item in result["review_items"]]
    lines += ["", "本底稿不作上诉期限、案由或胜诉结论，不是可直接提交的上诉状。", ""]
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
    Draft202012Validator(_load(root / "schemas" / "appeal-output.schema.json")).validate(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (temp / "appeal-review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "上诉审查工作底稿.md").write_text(markdown(result), encoding="utf-8")
        temp.replace(output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="生成待律师复核的上诉审查底稿")
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
