#!/usr/bin/env python3
"""校验源快照与要素映射之间的逐字来源关系。"""

from __future__ import annotations

from common import ConversionError, field_catalog, sha256_text


VALID_STATUSES = {"provided", "missing", "not_applicable", "conflict"}


def exact_span(text: str, quote: str, start: int | None, end: int | None) -> tuple[int, int] | None:
    if start is not None or end is not None:
        if start is None or end is None or start < 0 or end < start or text[start:end] != quote:
            return None
        return start, end
    positions: list[int] = []
    cursor = 0
    while quote:
        found = text.find(quote, cursor)
        if found < 0:
            break
        positions.append(found)
        cursor = found + 1
        if len(positions) > 1:
            break
    if len(positions) == 1:
        return positions[0], positions[0] + len(quote)
    return None


def validate_snapshot(snapshot: dict) -> list[str]:
    errors: list[str] = []
    text = snapshot.get("normalized_text", "")
    if snapshot.get("schema_version") != "1.0.0":
        errors.append("源快照 schema_version 必须为 1.0.0")
    if not text or snapshot.get("text_sha256") != sha256_text(text):
        errors.append("源快照文本哈希不匹配")
    source = snapshot.get("source", {})
    if source.get("ocr_used") is True and not source.get("human_verified"):
        errors.append("OCR 源文未完成人工核对")
    policy = snapshot.get("policy", {})
    expected_policy = {
        "claims": "verbatim",
        "facts": "verbatim",
        "missing_value": "leave_blank",
        "inference": "forbidden",
        "unmapped_content": "verbatim_appendix",
    }
    if policy != expected_policy:
        errors.append("源快照转换策略被修改")
    for unit in snapshot.get("units", []):
        start, end = unit.get("start"), unit.get("end")
        value = unit.get("text_verbatim", "")
        if not isinstance(start, int) or not isinstance(end, int) or text[start:end] != value:
            errors.append(f"源单元位置不匹配：{unit.get('unit_id', '未知')}")
        elif unit.get("sha256") != sha256_text(value):
            errors.append(f"源单元哈希不匹配：{unit.get('unit_id', '未知')}")
    return errors


def validate_mapping(snapshot: dict, mapping: dict, require_final: bool = False) -> dict:
    errors = validate_snapshot(snapshot)
    warnings: list[str] = []
    resolved_spans: dict[str, list[int]] = {}
    text = snapshot.get("normalized_text", "")

    if mapping.get("schema_version") != "1.0.0":
        errors.append("映射 schema_version 必须为 1.0.0")
    if mapping.get("source_text_sha256") != snapshot.get("text_sha256"):
        errors.append("映射与源快照哈希不一致")
    case_type = mapping.get("case_type")
    try:
        case_spec, expected_fields = field_catalog(case_type)
    except ConversionError as exc:
        errors.append(str(exc))
        case_spec, expected_fields = {}, []
    if snapshot.get("classification", {}).get("selected") != case_type:
        errors.append("映射案由与源快照确认案由不一致")
    if require_final and not mapping.get("case_type_human_confirmed"):
        errors.append("案由尚未由用户或承办律师确认")

    source_claims = snapshot.get("claims", [])
    mapped_claims = mapping.get("claims", [])
    source_claim_values = [item.get("text_verbatim") for item in source_claims]
    mapped_claim_values = [item.get("text_verbatim") for item in mapped_claims]
    if source_claim_values != mapped_claim_values:
        errors.append("诉讼请求发生增删、调序或改写")
    for index, item in enumerate(mapped_claims, start=1):
        value = item.get("text_verbatim", "")
        start, end = item.get("source_start"), item.get("source_end")
        if item.get("order") != index:
            errors.append(f"诉讼请求顺序编号不连续：第 {index} 项")
        if not isinstance(start, int) or not isinstance(end, int) or text[start:end] != value:
            errors.append(f"诉讼请求来源位置不匹配：第 {index} 项")
        if item.get("sha256") != sha256_text(value):
            errors.append(f"诉讼请求哈希不匹配：第 {index} 项")

    elements = mapping.get("elements", [])
    actual_ids = [item.get("field_id") for item in elements]
    expected_ids = [item["id"] for item in expected_fields]
    if actual_ids != expected_ids:
        errors.append("要素字段全集或顺序与字段目录不一致")
    for item in elements:
        field_id = item.get("field_id", "未知")
        status = item.get("status")
        value = item.get("value", "")
        quote = item.get("source_quote", "")
        if status not in VALID_STATUSES:
            errors.append(f"字段状态非法：{field_id}")
            continue
        if status == "missing":
            if value or quote or item.get("source_start") is not None or item.get("source_end") is not None:
                errors.append(f"缺失字段不得含值、摘录或位置：{field_id}")
        elif status == "provided":
            if not value or value != quote.strip():
                errors.append(f"已提供字段的值必须逐字等于原文摘录：{field_id}")
            span = exact_span(text, quote, item.get("source_start"), item.get("source_end"))
            if not span:
                errors.append(f"无法唯一或准确定位原文摘录：{field_id}")
            else:
                resolved_spans[field_id] = [span[0], span[1]]
        elif status == "not_applicable":
            if value:
                errors.append(f"不适用字段不得自动写入值：{field_id}")
            span = exact_span(text, quote, item.get("source_start"), item.get("source_end"))
            if not quote or not span:
                errors.append(f"不适用状态必须有可定位原文依据：{field_id}")
            else:
                resolved_spans[field_id] = [span[0], span[1]]
        elif status == "conflict":
            if not quote or not item.get("review_note"):
                errors.append(f"冲突字段必须保留原文和复核说明：{field_id}")
            if require_final:
                errors.append(f"冲突字段阻断生成：{field_id}")

    blockers = mapping.get("blockers", [])
    if require_final and blockers:
        errors.extend(f"阻断项：{item}" for item in blockers)

    mapped_ranges = [tuple(span) for span in resolved_spans.values()]
    claim_ranges = [(item.get("source_start", -1), item.get("source_end", -1)) for item in mapped_claims]
    uncovered: list[dict] = []
    unmapped = mapping.get("unmapped_segments", [])
    for index, item in enumerate(unmapped, start=1):
        value = item.get("text_verbatim", "")
        start, end = item.get("source_start"), item.get("source_end")
        if not isinstance(start, int) or not isinstance(end, int) or text[start:end] != value:
            errors.append(f"未映射片段来源位置不匹配：第 {index} 项")
            continue
        covered = any(start >= left and end <= right for left, right in mapped_ranges + claim_ranges)
        if not covered:
            uncovered.append(item)
            if require_final and not item.get("reviewed"):
                errors.append(f"未映射原文尚未人工复核：第 {index} 项")
    if uncovered:
        warnings.append(f"有 {len(uncovered)} 个原文片段将保留在附录")
    missing_count = sum(item.get("status") == "missing" for item in elements)
    if missing_count:
        warnings.append(f"有 {missing_count} 个要素在原文中缺失，正式表格保持空白")
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "case_type": case_type,
        "case_label": case_spec.get("label", ""),
        "resolved_spans": resolved_spans,
        "uncovered_segments": uncovered,
        "counts": {
            "claims": len(mapped_claims),
            "elements": len(elements),
            "provided": sum(item.get("status") == "provided" for item in elements),
            "missing": missing_count,
            "not_applicable": sum(item.get("status") == "not_applicable" for item in elements),
            "conflict": sum(item.get("status") == "conflict" for item in elements),
            "uncovered": len(uncovered),
        },
    }
