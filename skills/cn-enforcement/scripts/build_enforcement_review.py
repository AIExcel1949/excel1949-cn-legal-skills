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


def _dup(items: Iterable[dict[str, Any]], key: str, label: str) -> list[str]:
    values = _ids(items, key)
    return [f"{label}编号重复"] if len(values) != len(set(values)) else []


def _citations(value: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield value.get("execution_basis", {}).get("citation", {})
    effect_citation = value.get("execution_basis", {}).get("effect_review", {}).get("citation")
    if effect_citation:
        yield effect_citation
    yield from (item.get("citation", {}) for item in value.get("execution_basis", {}).get("obligations", []))
    yield from (item.get("citation", {}) for item in value.get("parties", []))
    yield from (item.get("citation", {}) for item in value.get("performance_records", []))
    yield from (item.get("citation", {}) for item in value.get("property_clues", []))
    for item in value.get("measure_candidates", []):
        yield from item.get("basis_citations", [])
    for item in value.get("procedure_nodes", []):
        yield from item.get("trigger_facts", [])


def validate(value: dict[str, Any], root: Path) -> list[str]:
    schema = _load(root / "schemas" / "enforcement-input.schema.json")
    errors = [error.message for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)]
    groups = (
        (value.get("sources", []), "source_id", "来源"), (value.get("authorities", []), "authority_id", "法源"),
        (value.get("parties", []), "party_id", "主体"), (value.get("performance_records", []), "record_id", "履行记录"),
        (value.get("amount_references", []), "amount_id", "金额引用"), (value.get("property_clues", []), "clue_id", "财产线索"),
        (value.get("measure_candidates", []), "candidate_id", "措施候选"), (value.get("procedure_nodes", []), "node_id", "程序节点"),
    )
    for items, key, label in groups:
        errors += _dup(items, key, label)
    obligations = value.get("execution_basis", {}).get("obligations", [])
    errors += _dup(obligations, "obligation_id", "履行内容")

    source_ids = set(_ids(value.get("sources", []), "source_id"))
    authority_ids = set(_ids(value.get("authorities", []), "authority_id"))
    party_ids = set(_ids(value.get("parties", []), "party_id"))
    obligation_ids = set(_ids(obligations, "obligation_id"))
    for citation in _citations(value):
        if citation.get("source_id") not in source_ids:
            errors.append(f"引用不存在来源：{citation.get('source_id')}")
    for item in obligations:
        for field in ("creditor_party_id", "debtor_party_id"):
            if item.get(field) not in party_ids:
                errors.append(f"履行内容引用不存在主体：{item.get(field)}")
    for item in value.get("performance_records", []):
        if item.get("obligation_id") not in obligation_ids:
            errors.append(f"履行记录引用不存在履行内容：{item.get('obligation_id')}")
    effect = value.get("execution_basis", {}).get("effect_review", {})
    if effect.get("status") == "unverified" and (effect.get("conclusion") is not None or effect.get("citation") is not None):
        errors.append("执行依据效力未核验时不得登记结论或引用")
    if effect.get("status") == "verified_by_lawyer" and (not effect.get("conclusion") or not effect.get("citation")):
        errors.append("执行依据效力已核验时必须登记结论与来源")
    for node in value.get("procedure_nodes", []):
        for rule in node.get("rule_inputs", []):
            if rule.get("authority_id") not in authority_ids:
                errors.append(f"程序节点引用不存在法源：{rule.get('authority_id')}")
        if node.get("lawyer_deadline_conclusion") is not None and not node.get("rule_inputs"):
            errors.append(f"程序期限结论必须引用已登记规则：{node.get('node_id')}")
    if value.get("external_action_requested"):
        errors.append("禁止自动查控、冻结、扣划、签章或提交")
    return sorted(set(errors))


def derive(value: dict[str, Any]) -> dict[str, Any]:
    amounts = [
        {
            "amount_id": item["amount_id"], "display_value": item["display_value"],
            "text_sha256": hashlib.sha256(item["display_value"].encode("utf-8")).hexdigest(),
            "calculation_artifact_id": item["calculation_artifact_id"], "artifact_sha256": item["artifact_sha256"],
            "locator": item["locator"], "recalculated": False,
        }
        for item in value["amount_references"]
    ]
    clues = [
        {
            "clue_id": item["clue_id"], "description": item["description"],
            "reported_verification_status": item["reported_verification_status"],
            "classification": "clue_only_not_confirmed_property", "status": "lawyer_review_required",
        }
        for item in value["property_clues"]
    ]
    measures = [
        {"candidate_id": item["candidate_id"], "measure_type": item["measure_type"], "status": "lawyer_review_required", "external_action_performed": False}
        for item in value["measure_candidates"]
    ]
    nodes = [
        {
            "node_id": item["node_id"], "node_type": item["node_type"], "trigger_facts": item["trigger_facts"],
            "rule_inputs": item["rule_inputs"], "lawyer_deadline_conclusion": item["lawyer_deadline_conclusion"],
            "automatic_deadline_calculation": None, "status": "lawyer_review_required",
        }
        for item in value["procedure_nodes"]
    ]
    reviews = [
        {"item_id": "ENF-BASIS", "question": "由律师确认执行依据生效、可执行性与权利义务主体", "status": "lawyer_review_required"},
        {"item_id": "ENF-PERFORMANCE", "question": "由律师核验已履行、未履行和争议履行记录", "status": "lawyer_review_required"},
        {"item_id": "ENF-AMOUNT", "question": "逐项核验外部计算成果、公式、日期、利率与文件哈希", "status": "lawyer_review_required"},
        {"item_id": "ENF-PROPERTY", "question": "将所有财产信息按线索核验，不得当作已确认财产", "status": "lawyer_review_required"},
        {"item_id": "ENF-PROCEDURE", "question": "由律师核验执行措施候选、异议或复议节点与期限", "status": "lawyer_review_required"},
    ]
    return {
        "schema_version": "1.0", "matter_id": value["matter_id"], "enforcement_id": value["enforcement_id"],
        "artifact_state": "lawyer_review_required", "basis_audit": value["execution_basis"], "party_audit": value["parties"],
        "performance_audit": value["performance_records"], "amount_bypass_audit": amounts, "property_clue_audit": clues,
        "measure_candidate_audit": measures, "procedure_node_audit": nodes, "review_items": reviews, "source_record": value,
    }


def markdown(result: dict[str, Any]) -> str:
    basis = result["basis_audit"]
    lines = ["# 执行申请审查工作底稿", "", f"案件编号：{result['matter_id']}  ", f"审查编号：{result['enforcement_id']}  ", "状态：待执业律师复核", "", "## 一、执行依据与履行内容", f"- 依据类型：{basis['basis_type']}", f"- 效力复核状态：{basis['effect_review']['status']}"]
    lines += [f"- {item['obligation_id']}：{item['verbatim_text']}" for item in basis["obligations"]]
    lines += ["", "## 二、权利义务主体"]
    lines += [f"- {item['party_id']}：{item['name']}（{item['role']}）" for item in result["party_audit"]]
    lines += ["", "## 三、履行状态"]
    lines += [f"- {item['record_id']}：{item['status']}；{item['description']}" for item in result["performance_audit"]] or ["- 未录入。"]
    lines += ["", "## 四、金额旁路引用（未重算）"]
    lines += [f"- {item['amount_id']}：{item['display_value']}；成果：{item['calculation_artifact_id']} / {item['locator']}" for item in result["amount_bypass_audit"]] or ["- 未录入金额成果。"]
    lines += ["", "## 五、财产线索（非已确认财产）"]
    lines += [f"- {item['clue_id']}：{item['description']}；状态：待律师核验线索" for item in result["property_clue_audit"]] or ["- 未录入。"]
    lines += ["", "## 六、执行措施申请候选"]
    lines += [f"- [ ] {item['candidate_id']}：{item['measure_type']}（未执行外部操作）" for item in result["measure_candidate_audit"]] or ["- 未录入。"]
    lines += ["", "## 七、异议或复议节点"]
    lines += [f"- {item['node_id']}：{item['node_type']}；自动期限计算：无" for item in result["procedure_node_audit"]] or ["- 未录入。"]
    lines += ["", "## 八、待律师复核"]
    lines += [f"- [ ] {item['question']}" for item in result["review_items"]]
    lines += ["", "本底稿不是可直接提交的执行申请书，未执行查控、冻结、扣划或其他外部操作。", ""]
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
    Draft202012Validator(_load(root / "schemas" / "enforcement-output.schema.json")).validate(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (temp / "enforcement-review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temp / "执行申请审查工作底稿.md").write_text(markdown(result), encoding="utf-8")
        temp.replace(output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="生成待律师复核的执行申请审查底稿")
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
