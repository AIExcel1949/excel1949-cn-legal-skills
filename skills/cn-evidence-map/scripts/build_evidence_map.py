#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


DIMENSIONS = ("authenticity", "legality", "relevance")
NON_DEFAULT_REVIEW = {"accepted", "disputed"}
HEARING_AUDIO_WORDS = ("庭审", "开庭", "法庭")
AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入根节点必须是对象")
    return value


def schema_errors(value: dict[str, Any], skill_root: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
    except ImportError:
        return ["缺少 jsonschema，无法执行结构校验"]

    core_schema_dir = skill_root.parent / "cn-legal-core" / "schemas"
    registry = Registry()
    for directory in (core_schema_dir, skill_root / "schemas"):
        for path in sorted(directory.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            if schema_id := schema.get("$id"):
                registry = registry.with_resource(schema_id, Resource.from_contents(schema))
    schema = json.loads((skill_root / "schemas" / "evidence-map.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    return [
        f"Schema {'.'.join(str(part) for part in error.path) or '<root>'}：{error.message}"
        for error in validator.iter_errors(value)
    ]


def output_schema_errors(value: dict[str, Any], skill_root: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
    except ImportError:
        return ["缺少 jsonschema，无法执行输出结构校验"]
    registry = Registry()
    for directory in (skill_root.parent / "cn-legal-core" / "schemas", skill_root / "schemas"):
        for path in sorted(directory.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            if schema_id := schema.get("$id"):
                registry = registry.with_resource(schema_id, Resource.from_contents(schema))
    schema = json.loads((skill_root / "schemas" / "evidence-map-output.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    return [
        f"输出 Schema {'.'.join(str(part) for part in error.path) or '<root>'}：{error.message}"
        for error in validator.iter_errors(value)
    ]


def duplicate_ids(items: Iterable[dict[str, Any]], key: str) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        value = item.get(key)
        if not value:
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def spans_from(value: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    collections = (
        ("facts", "source_spans"),
        ("claims", "source_spans"),
        ("defenses", "source_spans"),
        ("declared_conflicts", "source_spans"),
        ("three_nature_reviews", "source_spans"),
        ("evidence_fact_links", "source_spans"),
    )
    for collection, field in collections:
        for index, item in enumerate(value.get(collection, [])):
            for span_index, span in enumerate(item.get(field, [])):
                yield f"{collection}[{index}].{field}[{span_index}]", span
    for index, link in enumerate(value.get("evidence_fact_links", [])):
        purpose = link.get("proof_purpose") or {}
        for span_index, span in enumerate(purpose.get("source_spans", [])):
            yield f"evidence_fact_links[{index}].proof_purpose.source_spans[{span_index}]", span


def validate(value: dict[str, Any], skill_root: Path) -> dict[str, Any]:
    errors = schema_errors(value, skill_root)
    warnings: list[str] = []

    collections = {
        "sources": ("source_id", value.get("sources", [])),
        "facts": ("fact_id", value.get("facts", [])),
        "issues": ("issue_id", value.get("issues", [])),
        "claims": ("claim_id", value.get("claims", [])),
        "defenses": ("defense_id", value.get("defenses", [])),
        "evidence": ("evidence_id", value.get("evidence", [])),
        "evidence_fact_links": ("link_id", value.get("evidence_fact_links", [])),
        "fact_issue_links": ("link_id", value.get("fact_issue_links", [])),
        "fact_position_links": ("link_id", value.get("fact_position_links", [])),
        "three_nature_reviews": ("review_id", value.get("three_nature_reviews", [])),
        "declared_conflicts": ("conflict_id", value.get("declared_conflicts", [])),
    }
    for name, (key, items) in collections.items():
        duplicates = duplicate_ids(items, key)
        if duplicates:
            errors.append(f"{name} 编号重复：{'、'.join(duplicates)}")

    source_ids = {item.get("source_id") for item in value.get("sources", [])}
    fact_ids = {item.get("fact_id") for item in value.get("facts", [])}
    issue_ids = {item.get("issue_id") for item in value.get("issues", [])}
    claim_ids = {item.get("claim_id") for item in value.get("claims", [])}
    defense_ids = {item.get("defense_id") for item in value.get("defenses", [])}
    evidence_ids = {item.get("evidence_id") for item in value.get("evidence", [])}

    for source in value.get("sources", []):
        file_name = str(source.get("file_name", ""))
        mime_type = str(source.get("mime_type", "")).lower()
        audio = mime_type.startswith("audio/") or Path(file_name).suffix.lower() in AUDIO_SUFFIXES
        if audio and any(word in file_name for word in HEARING_AUDIO_WORDS):
            errors.append(f"禁止处理庭审录音来源：{source.get('source_id', '未知来源')}｜{file_name}")

    for location, span in spans_from(value):
        source_id = span.get("source_id")
        if source_id not in source_ids:
            errors.append(f"{location} 引用不存在的来源：{source_id}")
        if not str(span.get("quote", "")).strip():
            errors.append(f"{location} 缺少非空原文引文")
        if not any(key in span for key in ("page", "paragraph", "start", "end")):
            errors.append(f"{location} 缺少页码、段落或字符位置")

    evidence_to_facts: dict[str, set[str]] = defaultdict(set)
    for link in value.get("evidence_fact_links", []):
        link_id = link.get("link_id", "未知关系")
        evidence_id = link.get("evidence_id")
        fact_id = link.get("fact_id")
        if evidence_id not in evidence_ids:
            errors.append(f"{link_id} 引用不存在的证据：{evidence_id}")
        if fact_id not in fact_ids:
            errors.append(f"{link_id} 引用不存在的事实：{fact_id}")
        evidence_to_facts[evidence_id].add(fact_id)
        if link.get("status") == "source_stated" and not link.get("source_spans"):
            errors.append(f"{link_id} 标记为 source_stated 但缺少来源定位")
        if link.get("status") == "human_confirmed" and not link.get("confirmation_note"):
            errors.append(f"{link_id} 标记为 human_confirmed 但缺少确认说明")
        purpose = link.get("proof_purpose")
        if purpose:
            if purpose.get("basis_status") == "source_stated" and not purpose.get("source_spans"):
                errors.append(f"{link_id} 的证明目的标记为 source_stated 但缺少原文定位")
            if purpose.get("basis_status") == "human_confirmed" and not purpose.get("confirmation_note"):
                errors.append(f"{link_id} 的证明目的标记为 human_confirmed 但缺少确认说明")

    for evidence in value.get("evidence", []):
        evidence_id = evidence.get("evidence_id")
        if evidence.get("source_id") not in source_ids:
            errors.append(f"{evidence_id} 引用不存在的来源：{evidence.get('source_id')}")
        declared = set(evidence.get("fact_ids", []))
        linked = evidence_to_facts.get(evidence_id, set())
        if declared != linked:
            errors.append(
                f"{evidence_id} 的 fact_ids 与 evidence_fact_links 不一致："
                f"fact_ids={sorted(declared)}，links={sorted(linked)}"
            )

    for link in value.get("fact_issue_links", []):
        link_id = link.get("link_id", "未知关系")
        if link.get("fact_id") not in fact_ids:
            errors.append(f"{link_id} 引用不存在的事实：{link.get('fact_id')}")
        if link.get("issue_id") not in issue_ids:
            errors.append(f"{link_id} 引用不存在的争点：{link.get('issue_id')}")
        if link.get("status") == "human_confirmed" and not link.get("confirmation_note"):
            errors.append(f"{link_id} 标记为 human_confirmed 但缺少确认说明")

    for link in value.get("fact_position_links", []):
        link_id = link.get("link_id", "未知关系")
        if link.get("fact_id") not in fact_ids:
            errors.append(f"{link_id} 引用不存在的事实：{link.get('fact_id')}")
        target_type = link.get("target_type")
        target_id = link.get("target_id")
        valid_ids = claim_ids if target_type == "claim" else defense_ids
        if target_id not in valid_ids:
            errors.append(f"{link_id} 引用不存在的{('诉请' if target_type == 'claim' else '抗辩')}：{target_id}")
        if link.get("status") == "human_confirmed" and not link.get("confirmation_note"):
            errors.append(f"{link_id} 标记为 human_confirmed 但缺少确认说明")

    review_keys: set[tuple[str, str]] = set()
    review_status: dict[tuple[str, str], str] = {}
    for review in value.get("three_nature_reviews", []):
        review_id = review.get("review_id", "未知审查")
        evidence_id = review.get("evidence_id")
        if evidence_id not in evidence_ids:
            errors.append(f"{review_id} 引用不存在的证据：{evidence_id}")
        key = (evidence_id, review.get("dimension"))
        if key in review_keys:
            errors.append(f"同一证据维度存在多条生效审查记录：{evidence_id}｜{review.get('dimension')}")
        review_keys.add(key)
        review_status[key] = review.get("status")

    for evidence in value.get("evidence", []):
        evidence_id = evidence.get("evidence_id")
        for dimension in DIMENSIONS:
            status = evidence.get(dimension)
            if status in NON_DEFAULT_REVIEW and review_status.get((evidence_id, dimension)) != status:
                errors.append(f"{evidence_id} 的 {dimension}={status} 缺少一致的人工确认记录")

    for conflict in value.get("declared_conflicts", []):
        conflict_id = conflict.get("conflict_id", "未知冲突")
        for fact_id in conflict.get("fact_ids", []):
            if fact_id not in fact_ids:
                errors.append(f"{conflict_id} 引用不存在的事实：{fact_id}")
        if conflict.get("status") == "resolved" and not conflict.get("resolution_note"):
            errors.append(f"{conflict_id} 标记为 resolved 但缺少处理说明")

    if not value.get("evidence"):
        warnings.append("没有证据记录，报告只会显示结构缺口")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _json_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_result(value: dict[str, Any]) -> dict[str, Any]:
    facts = {item["fact_id"]: item for item in value["facts"]}
    evidence = {item["evidence_id"]: item for item in value["evidence"]}
    sources = {item["source_id"]: item for item in value["sources"]}

    evidence_to_facts: dict[str, set[str]] = defaultdict(set)
    fact_to_evidence: dict[str, set[str]] = defaultdict(set)
    purposes: dict[tuple[str, str], dict[str, Any]] = {}
    source_locations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in value["evidence_fact_links"]:
        evidence_id, fact_id = link["evidence_id"], link["fact_id"]
        evidence_to_facts[evidence_id].add(fact_id)
        fact_to_evidence[fact_id].add(evidence_id)
        source_locations[evidence_id].extend(link.get("source_spans", []))
        if purpose := link.get("proof_purpose"):
            purposes[(evidence_id, fact_id)] = purpose
            source_locations[evidence_id].extend(purpose.get("source_spans", []))

    fact_to_issues: dict[str, set[str]] = defaultdict(set)
    issue_to_facts: dict[str, set[str]] = defaultdict(set)
    for link in value["fact_issue_links"]:
        fact_to_issues[link["fact_id"]].add(link["issue_id"])
        issue_to_facts[link["issue_id"]].add(link["fact_id"])

    fact_to_positions: dict[str, set[str]] = defaultdict(set)
    position_to_facts: dict[str, set[str]] = defaultdict(set)
    for link in value["fact_position_links"]:
        position = f"{link['target_type']}:{link['target_id']}"
        fact_to_positions[link["fact_id"]].add(position)
        position_to_facts[position].add(link["fact_id"])

    matrix: list[dict[str, Any]] = []
    for evidence_id in sorted(evidence):
        item = evidence[evidence_id]
        fact_ids = sorted(evidence_to_facts.get(evidence_id, set()))
        issue_ids = sorted({issue for fact_id in fact_ids for issue in fact_to_issues.get(fact_id, set())})
        position_ids = sorted({position for fact_id in fact_ids for position in fact_to_positions.get(fact_id, set())})
        matrix.append(
            {
                "evidence_id": evidence_id,
                "name": item["name"],
                "source_id": item["source_id"],
                "source_file": sources[item["source_id"]]["file_name"],
                "source_sha256": sources[item["source_id"]]["sha256"],
                "fact_ids": fact_ids,
                "issue_ids": issue_ids,
                "position_ids": position_ids,
                "proof_purposes": [
                    {"fact_id": fact_id, **purposes[(evidence_id, fact_id)]}
                    for fact_id in fact_ids
                    if (evidence_id, fact_id) in purposes
                ],
                "three_nature": {dimension: item.get(dimension, "unknown") for dimension in DIMENSIONS},
                "verification_status": item["verification_status"],
                "source_locations": source_locations.get(evidence_id, []),
            }
        )

    gaps: list[dict[str, Any]] = []
    for fact_id in sorted(facts):
        if not fact_to_evidence.get(fact_id):
            gaps.append({"gap_type": "fact_without_evidence", "target_id": fact_id})
    for issue in sorted(value["issues"], key=lambda item: item["issue_id"]):
        issue_id = issue["issue_id"]
        linked_facts = issue_to_facts.get(issue_id, set())
        if not linked_facts:
            gaps.append({"gap_type": "issue_without_fact", "target_id": issue_id})
        elif not any(fact_to_evidence.get(fact_id) for fact_id in linked_facts):
            gaps.append({"gap_type": "issue_without_evidence", "target_id": issue_id})
    positions = [("claim", item["claim_id"]) for item in value["claims"]]
    positions.extend(("defense", item["defense_id"]) for item in value["defenses"])
    for target_type, target_id in sorted(positions):
        position = f"{target_type}:{target_id}"
        linked_facts = position_to_facts.get(position, set())
        if not linked_facts:
            gaps.append({"gap_type": "position_without_fact", "target_id": position})
        elif not any(fact_to_evidence.get(fact_id) for fact_id in linked_facts):
            gaps.append({"gap_type": "position_without_evidence", "target_id": position})
    for link in sorted(value["evidence_fact_links"], key=lambda item: item["link_id"]):
        if not link.get("proof_purpose"):
            gaps.append({"gap_type": "proof_purpose_unconfirmed", "target_id": link["link_id"]})
    for evidence_id in sorted(evidence):
        pending = [dimension for dimension in DIMENSIONS if evidence[evidence_id].get(dimension) in {"unreviewed", "unknown", None}]
        if pending:
            gaps.append(
                {
                    "gap_type": "three_nature_unreviewed",
                    "target_id": evidence_id,
                    "dimensions": pending,
                }
            )

    conflicts: list[dict[str, Any]] = []
    for conflict in value["declared_conflicts"]:
        conflicts.append(
            {
                "conflict_id": conflict["conflict_id"],
                "kind": "declared",
                "fact_ids": sorted(conflict["fact_ids"]),
                "reason": conflict["description"],
                "status": conflict["status"],
                "source_spans": conflict["source_spans"],
            }
        )
    for fact in value["facts"]:
        if fact["status"] == "conflict":
            conflicts.append(
                {
                    "conflict_id": f"auto-status-{fact['fact_id']}",
                    "kind": "status_flag",
                    "fact_ids": [fact["fact_id"]],
                    "reason": "事实记录已标记为 conflict，须人工核实",
                    "status": "candidate",
                    "source_spans": fact["source_spans"],
                }
            )
    by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in value["facts"]:
        if fact.get("field"):
            by_field[fact["field"]].append(fact)
    for field, items in sorted(by_field.items()):
        values: dict[str, list[str]] = defaultdict(list)
        for fact in items:
            compared = fact.get("normalized_value", fact.get("raw_value"))
            values[_json_key(compared)].append(fact["fact_id"])
        if len(values) > 1:
            conflicts.append(
                {
                    "conflict_id": f"auto-field-{len(conflicts) + 1:04d}",
                    "kind": "same_field_different_value",
                    "fact_ids": sorted(fact_id for group in values.values() for fact_id in group),
                    "reason": f"同一字段“{field}”存在不同记录值，仅作为潜在冲突提示",
                    "status": "candidate",
                    "source_spans": [
                        span
                        for item in items
                        for span in item.get("source_spans", [])
                    ],
                }
            )

    result = copy.deepcopy(value)
    result.update(
        {
            "matrix": matrix,
            "gaps": gaps,
            "potential_conflicts": conflicts,
            "coverage": {
                "evidence_count": len(evidence),
                "fact_count": len(facts),
                "facts_with_evidence": sum(bool(fact_to_evidence.get(fact_id)) for fact_id in facts),
                "issue_count": len(value["issues"]),
                "issues_with_evidence": sum(
                    any(fact_to_evidence.get(fact_id) for fact_id in issue_to_facts.get(item["issue_id"], set()))
                    for item in value["issues"]
                ),
                "position_count": len(positions),
                "positions_with_evidence": sum(
                    any(fact_to_evidence.get(fact_id) for fact_id in position_to_facts.get(f"{kind}:{target_id}", set()))
                    for kind, target_id in positions
                ),
            },
            "artifact_state": "lawyer_review_required",
            "legal_notice": "结构化链接不等于证明力或三性结论，须由执业律师逐项核验。",
        }
    )
    return result


def csv_text(result: dict[str, Any]) -> str:
    stream = io.StringIO(newline="")
    fields = [
        "evidence_id", "name", "source_id", "source_file", "source_sha256",
        "fact_ids", "issue_ids", "position_ids", "proof_purposes",
        "authenticity", "legality", "relevance", "verification_status", "source_locations",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for item in result["matrix"]:
        writer.writerow(
            {
                "evidence_id": item["evidence_id"],
                "name": item["name"],
                "source_id": item["source_id"],
                "source_file": item["source_file"],
                "source_sha256": item["source_sha256"],
                "fact_ids": "；".join(item["fact_ids"]),
                "issue_ids": "；".join(item["issue_ids"]),
                "position_ids": "；".join(item["position_ids"]),
                "proof_purposes": "；".join(
                    f"{purpose['fact_id']}：{purpose['text']}（{purpose['basis_status']}）"
                    for purpose in item["proof_purposes"]
                ),
                "authenticity": item["three_nature"]["authenticity"],
                "legality": item["three_nature"]["legality"],
                "relevance": item["three_nature"]["relevance"],
                "verification_status": item["verification_status"],
                "source_locations": "；".join(
                    f"{span['source_id']}@{span.get('page', span.get('paragraph', span.get('start', '待定位')))}：{span['quote']}"
                    for span in item["source_locations"]
                ),
            }
        )
    return stream.getvalue()


def markdown(result: dict[str, Any]) -> str:
    coverage = result["coverage"]
    lines = [
        "# 证据映射报告",
        "",
        f"案件编号：{result['matter_id']}  ",
        f"映射编号：{result['map_id']}  ",
        f"材料截止日期：{result['cutoff_date']}  ",
        "状态：须执业律师复核",
        "",
        "> 结构化链接不等于证明力或三性结论，不得直接据此认定案件事实。",
        "",
        "## 一、覆盖概况",
        "",
        f"- 证据：{coverage['evidence_count']} 项。",
        f"- 待证事实：{coverage['facts_with_evidence']}/{coverage['fact_count']} 项存在证据链接。",
        f"- 争点：{coverage['issues_with_evidence']}/{coverage['issue_count']} 项可经事实链接至证据。",
        f"- 诉请或抗辩：{coverage['positions_with_evidence']}/{coverage['position_count']} 项可经事实链接至证据。",
        "",
        "## 二、证据矩阵",
        "",
    ]
    if not result["matrix"]:
        lines.append("- 尚无证据记录。")
    for item in result["matrix"]:
        purposes = "；".join(purpose["text"] for purpose in item["proof_purposes"]) or "未确认"
        nature = item["three_nature"]
        lines.extend(
            [
                f"### {item['evidence_id']}｜{item['name']}",
                "",
                f"- 来源：{item['source_id']}｜{item['source_file']}｜SHA-256 {item['source_sha256']}",
                f"- 待证事实：{'、'.join(item['fact_ids']) or '未建立链接'}",
                f"- 争点：{'、'.join(item['issue_ids']) or '未建立链接'}",
                f"- 诉请或抗辩：{'、'.join(item['position_ids']) or '未建立链接'}",
                f"- 证明目的：{purposes}",
                f"- 三性状态：真实性 {nature['authenticity']}；合法性 {nature['legality']}；关联性 {nature['relevance']}",
                "",
            ]
        )
    lines.extend(["## 三、证据缺口", ""])
    if result["gaps"]:
        for gap in result["gaps"]:
            dimensions = f"｜{ '、'.join(gap.get('dimensions', []))}" if gap.get("dimensions") else ""
            lines.append(f"- {gap['gap_type']}｜{gap['target_id']}{dimensions}")
    else:
        lines.append("- 未发现机器可识别的结构断链；仍须人工核验实质证明问题。")
    lines.extend(["", "## 四、潜在冲突", ""])
    if result["potential_conflicts"]:
        for conflict in result["potential_conflicts"]:
            lines.append(
                f"- {conflict['conflict_id']}｜{'、'.join(conflict['fact_ids'])}｜"
                f"{conflict['reason']}｜{conflict['status']}"
            )
    else:
        lines.append("- 未发现机器可识别的潜在冲突；不代表材料不存在实质矛盾。")
    lines.extend(
        [
            "",
            "## 五、人工复核要求",
            "",
            "- 逐项核验证明目的是否来自材料原文或用户明确确认。",
            "- 逐项审查真实性、合法性、关联性和证据证明力。",
            "- 核验争点、举证责任、证明标准及诉请或抗辩关系。",
            "- AI 生成内容仅供学习参考，不得直接提交法院或对方当事人。",
        ]
    )
    return "\n".join(lines) + "\n"


def build(input_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    value = load_json(input_path)
    skill_root = Path(__file__).resolve().parent.parent
    validation = validate(value, skill_root)
    if not validation["ok"]:
        raise ValueError("；".join(validation["errors"]))
    result = build_result(value)
    output_errors = output_schema_errors(result, skill_root)
    if output_errors:
        raise ValueError("；".join(output_errors))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-evidence-map-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        (temp / "evidence-map.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (temp / "validation.json").write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (temp / "evidence-matrix.csv").write_text(csv_text(result), encoding="utf-8", newline="")
        (temp / "证据映射报告.md").write_text(markdown(result), encoding="utf-8")
        temp.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成中国法律案件证据—事实—争点—诉请或抗辩映射")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.input, args.output)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] 已生成证据映射：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
