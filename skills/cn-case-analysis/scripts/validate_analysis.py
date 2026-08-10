#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


CORE_SCHEMA_NAMES = (
    "common",
    "party",
    "claim",
    "fact-ledger",
    "issue",
    "evidence",
    "authority",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入根节点必须是对象")
    return value


def _schema_errors(value: dict[str, Any], skill_root: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
    except ImportError:
        return ["缺少 jsonschema 或 referencing，无法执行结构校验"]

    core_root = skill_root.parent / "cn-legal-core" / "schemas"
    registry = Registry()
    for name in CORE_SCHEMA_NAMES:
        schema = json.loads((core_root / f"{name}.schema.json").read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = json.loads((skill_root / "schemas" / "analysis-input.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    return [
        f"Schema {'.'.join(str(part) for part in error.absolute_path) or '<root>'}：{error.message}"
        for error in sorted(validator.iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
    ]


def _duplicates(items: Iterable[dict[str, Any]], key: str) -> list[str]:
    values = [str(item.get(key, "")) for item in items if item.get(key)]
    return sorted({value for value in values if values.count(value) > 1})


def _check_refs(
    errors: list[str], owner: str, label: str, values: Iterable[str], allowed: set[str]
) -> None:
    missing = sorted(set(values) - allowed)
    if missing:
        errors.append(f"{owner} 引用了不存在的{label}：{'、'.join(missing)}")


def _has_parent_cycle(parent_by_issue: dict[str, str | None]) -> bool:
    for start in sorted(parent_by_issue):
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                return True
            seen.add(current)
            current = parent_by_issue.get(current)
    return False


def validate(value: dict[str, Any], skill_root: Path | None = None) -> dict[str, Any]:
    root = skill_root or Path(__file__).resolve().parent.parent
    errors = _schema_errors(value, root)
    warnings: list[str] = []
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    collections = {
        "当事人": (value["parties"], "party_id"),
        "请求": (value["claims"], "claim_id"),
        "事实": (value["facts"], "fact_id"),
        "争点": (value["issues"], "issue_id"),
        "证据": (value["evidence"], "evidence_id"),
        "法源": (value["authorities"], "authority_id"),
        "分析争点": (value["issue_analyses"], "issue_id"),
        "待确认事项": (value["pending_confirmations"], "confirmation_id"),
        "律师判断": (value["lawyer_judgments"], "judgment_id"),
        "领域知识包": (value["domain_packs"], "pack_id"),
    }
    for label, (items, key) in collections.items():
        duplicate_ids = _duplicates(items, key)
        if duplicate_ids:
            errors.append(f"{label}编号重复：{'、'.join(duplicate_ids)}")

    parties = {item["party_id"] for item in value["parties"]}
    claims = {item["claim_id"] for item in value["claims"]}
    facts = {item["fact_id"] for item in value["facts"]}
    issues = {item["issue_id"] for item in value["issues"]}
    evidence = {item["evidence_id"] for item in value["evidence"]}
    authorities = {item["authority_id"] for item in value["authorities"]}
    analyses = {item["issue_id"] for item in value["issue_analyses"]}
    if issues != analyses:
        missing_analysis = sorted(issues - analyses)
        unknown_analysis = sorted(analyses - issues)
        if missing_analysis:
            errors.append(f"争点缺少分析节点：{'、'.join(missing_analysis)}")
        if unknown_analysis:
            errors.append(f"分析节点不存在于核心争点：{'、'.join(unknown_analysis)}")

    nested: dict[str, list[dict[str, Any]]] = {"positions": [], "elements": [], "risks": [], "research": []}
    parent_by_issue: dict[str, str | None] = {}
    core_issue_by_id = {item["issue_id"]: item for item in value["issues"]}
    all_nested_ids: set[str] = set()
    for analysis in value["issue_analyses"]:
        issue_id = analysis["issue_id"]
        parent_id = analysis["parent_issue_id"]
        parent_by_issue[issue_id] = parent_id
        if parent_id is not None and parent_id not in issues:
            errors.append(f"{issue_id} 的父争点不存在：{parent_id}")
        if parent_id == issue_id:
            errors.append(f"{issue_id} 不得以自身为父争点")
        _check_refs(errors, issue_id, "请求", analysis["claim_ids"], claims)
        nested["positions"].extend(analysis["positions"])
        nested["elements"].extend(analysis["elements"])
        nested["risks"].extend(analysis["risks"])
        nested["research"].extend(analysis["research_items"])

        element_ids = {item["element_id"] for item in analysis["elements"]}
        declared_ids = set(core_issue_by_id.get(issue_id, {}).get("element_ids", []))
        if declared_ids and declared_ids != element_ids:
            errors.append(f"{issue_id} 的核心 element_ids 与要件矩阵不一致")
        for position in analysis["positions"]:
            owner = position["position_id"]
            _check_refs(errors, owner, "当事人", [position["party_id"]], parties)
            _check_refs(errors, owner, "事实", position["fact_ids"], facts)
            _check_refs(errors, owner, "证据", position["evidence_ids"], evidence)
            _check_refs(errors, owner, "法源", position["authority_ids"], authorities)
        for element in analysis["elements"]:
            owner = element["element_id"]
            _check_refs(errors, owner, "举证责任主体", element["burden_party_ids"], parties)
            _check_refs(errors, owner, "事实", element["fact_ids"], facts)
            _check_refs(errors, owner, "证据", element["evidence_ids"], evidence)
            _check_refs(errors, owner, "法源", element["authority_ids"], authorities)

    if _has_parent_cycle(parent_by_issue):
        errors.append("争点树存在环")

    nested_key_map = {"positions": "position_id", "elements": "element_id", "risks": "risk_id", "research": "research_id"}
    for label, key in nested_key_map.items():
        duplicate_ids = _duplicates(nested[label], key)
        if duplicate_ids:
            errors.append(f"{label} 编号重复：{'、'.join(duplicate_ids)}")
        all_nested_ids.update(str(item[key]) for item in nested[label])

    all_referenceable = parties | claims | facts | issues | evidence | authorities | all_nested_ids
    for risk in nested["risks"]:
        _check_refs(errors, risk["risk_id"], "关联对象", risk["related_ids"], all_referenceable)
    for item in value["pending_confirmations"]:
        _check_refs(errors, item["confirmation_id"], "事实", item["related_fact_ids"], facts)

    frames = {item["frame"] for item in value["issue_analyses"]}
    for frame, label in (("claim_right", "请求权"), ("defense", "抗辩"), ("procedure", "程序")):
        if frame not in frames:
            warnings.append(f"尚未建立{label}分析节点，应确认是否确实不适用")
    for authority in value["authorities"]:
        if authority["effect_status"] == "unknown":
            warnings.append(f"法源 {authority['authority_id']} 效力状态待核验")
    if not value["lawyer_judgments"]:
        warnings.append("尚未登记律师判断问题，机器报告不得以此作为最终结论")

    return {"ok": not errors, "errors": errors, "warnings": sorted(set(warnings))}


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"输出文件已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.link(temp_name, path)
        Path(temp_name).unlink()
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="校验中国案件中立分析输入")
    parser.add_argument("input", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = validate(load_json(args.input))
        if args.report:
            atomic_write_json(args.report, result)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    stream = sys.stdout if result["ok"] else sys.stderr
    print(json.dumps(result, ensure_ascii=False, indent=2), file=stream)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
