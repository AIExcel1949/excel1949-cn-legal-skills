#!/usr/bin/env python3
"""只读解析传统起诉状并建立字符级源快照。"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from common import (
    CONFIG_DIR,
    SAFE_DOCX_MIME,
    ConversionError,
    assert_safe_docx,
    detect_mime,
    field_catalog,
    load_json,
    normalize_text,
    sha256_bytes,
    sha256_text,
)


HEADING_PATTERNS = {
    "claims": re.compile(r"^\s*诉讼请求\s*[：:]?\s*$", re.M),
    "facts": re.compile(r"^\s*事实与理由\s*[：:]?\s*$", re.M),
    "evidence": re.compile(r"^\s*(?:证据和证据来源|证据清单)\s*[：:]?\s*$", re.M),
    "court": re.compile(r"^\s*此致\s*$", re.M),
    "signature": re.compile(r"^\s*(?:具状人|起诉人)\s*[：:]?", re.M),
}
CLAIM_ITEM_RE = re.compile(
    r"(?ms)^\s*(?:第\s*)?([0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*[\.．、]\s*(.+?)(?=^\s*(?:第\s*)?(?:[0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*[\.．、]|\Z)"
)


def extract_docx_units(path: Path) -> list[tuple[str, str]]:
    assert_safe_docx(path)
    document = Document(path)
    units: list[tuple[str, str]] = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            units.append(("paragraph", normalize_text(paragraph.text)))
    for table in document.tables:
        for row in table.rows:
            cells = [normalize_text(cell.text) for cell in row.cells]
            row_text = "｜".join(value for value in cells if value)
            if row_text.strip():
                units.append(("table_row", row_text))
    return units


def extract_text_units(path: Path) -> list[tuple[str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConversionError("文本文件必须使用 UTF-8 编码") from exc
    return [("paragraph", normalize_text(line)) for line in text.splitlines() if line.strip()]


def assemble_units(raw_units: list[tuple[str, str]]) -> tuple[str, list[dict]]:
    parts: list[str] = []
    units: list[dict] = []
    offset = 0
    for ordinal, (kind, text) in enumerate(raw_units, start=1):
        if parts:
            parts.append("\n")
            offset += 1
        start = offset
        parts.append(text)
        offset += len(text)
        units.append(
            {
                "unit_id": f"U{ordinal:06d}",
                "ordinal": ordinal,
                "kind": kind,
                "text_verbatim": text,
                "start": start,
                "end": offset,
                "sha256": sha256_text(text),
            }
        )
    return "".join(parts), units


def locate_sections(text: str) -> dict[str, dict]:
    headings: list[tuple[str, re.Match[str]]] = []
    for name, pattern in HEADING_PATTERNS.items():
        match = pattern.search(text)
        if match:
            headings.append((name, match))
    headings.sort(key=lambda item: item[1].start())
    sections: dict[str, dict] = {}
    for index, (name, match) in enumerate(headings):
        start = match.end()
        end = headings[index + 1][1].start() if index + 1 < len(headings) else len(text)
        while start < end and text[start] in " \t\n：:":
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        value = text[start:end]
        sections[name] = {
            "start": start,
            "end": end,
            "text_verbatim": value,
            "sha256": sha256_text(value),
        }
    if "claims" not in sections or "facts" not in sections:
        raise ConversionError("未识别到独立的“诉讼请求”和“事实与理由”标题，请先人工整理源文结构")
    first_heading = min(match.start() for _, match in headings)
    sections["parties"] = {
        "start": 0,
        "end": first_heading,
        "text_verbatim": text[:first_heading].rstrip(),
        "sha256": sha256_text(text[:first_heading].rstrip()),
    }
    return sections


def extract_claims(text: str, section: dict) -> list[dict]:
    section_text = section["text_verbatim"]
    claims: list[dict] = []
    for match in CLAIM_ITEM_RE.finditer(section_text):
        value = match.group(2).strip()
        local_start = match.start(2) + len(match.group(2)) - len(match.group(2).lstrip())
        start = section["start"] + local_start
        end = start + len(value)
        claims.append(
            {
                "order": len(claims) + 1,
                "text_verbatim": value,
                "start": start,
                "end": end,
                "sha256": sha256_text(value),
            }
        )
    if not claims and section_text.strip():
        value = section_text.strip()
        start = text.find(value, section["start"], section["end"])
        claims.append(
            {"order": 1, "text_verbatim": value, "start": start, "end": start + len(value), "sha256": sha256_text(value)}
        )
    return claims


def classify(text: str) -> dict:
    config = load_json(CONFIG_DIR / "case-keywords.json")
    candidates: list[dict] = []
    for case_type, spec in config["case_types"].items():
        score = 0
        matches: list[str] = []
        for keyword, weight in spec["keywords"].items():
            count = text.count(keyword)
            if count:
                score += weight * min(count, 3)
                matches.append(keyword)
        candidates.append({"case_type": case_type, "label": spec["label"], "score": score, "matches": matches})
    candidates.sort(key=lambda item: item["score"], reverse=True)
    total = sum(item["score"] for item in candidates)
    top = candidates[0]
    second = candidates[1]
    confidence = round(top["score"] / total, 4) if total else 0.0
    selected = top["case_type"] if top["score"] >= 8 and top["score"] >= second["score"] + 3 else "unknown"
    return {"selected": selected, "confidence": confidence, "human_confirmed": False, "candidates": candidates}


def build_snapshot(path: Path, case_type: str | None = None) -> dict:
    if not path.is_file():
        raise ConversionError(f"源文件不存在：{path}")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ConversionError("源文件超过 20 MB 限制")
    mime = detect_mime(path)
    if mime == SAFE_DOCX_MIME:
        raw_units = extract_docx_units(path)
    elif mime in {"text/plain", "text/markdown"}:
        raw_units = extract_text_units(path)
    else:
        raise ConversionError("仅支持 UTF-8 的 .txt、.md 和无宏、无外部关系的 .docx")
    if not raw_units:
        raise ConversionError("源文件没有可提取文本")
    text, units = assemble_units(raw_units)
    sections = locate_sections(text)
    claims = extract_claims(text, sections["claims"])
    classification = classify(text)
    if case_type:
        field_catalog(case_type)
        classification["selected"] = case_type
        classification["confidence"] = 1.0
        classification["human_confirmed"] = True
    return {
        "schema_version": "1.0.0",
        "source": {
            "file_name": path.name,
            "mime_type": mime,
            "file_sha256": sha256_bytes(path.read_bytes()),
            "ocr_used": False,
            "human_verified": True,
        },
        "normalized_text": text,
        "text_sha256": sha256_text(text),
        "units": units,
        "sections": sections,
        "claims": claims,
        "classification": classification,
        "policy": {
            "claims": "verbatim",
            "facts": "verbatim",
            "missing_value": "leave_blank",
            "inference": "forbidden",
            "unmapped_content": "verbatim_appendix",
        },
    }


def build_mapping_skeleton(snapshot: dict) -> dict:
    case_type = snapshot["classification"]["selected"]
    if case_type == "unknown":
        raise ConversionError("案由识别置信度不足，请使用 --case-type 由律师确认案由")
    _, fields = field_catalog(case_type)
    elements = []
    for field in fields:
        item = {
            "field_id": field["id"],
            "section": field["section"],
            "label": field["label"],
            "status": "missing",
            "value": "",
            "source_quote": "",
            "source_start": None,
            "source_end": None,
            "review_note": "",
        }
        if field["id"] == "claim.fulltext":
            span = snapshot["sections"]["claims"]
            item.update(status="provided", value=span["text_verbatim"], source_quote=span["text_verbatim"], source_start=span["start"], source_end=span["end"])
        elif field["id"] == "fact.fulltext":
            span = snapshot["sections"]["facts"]
            item.update(status="provided", value=span["text_verbatim"], source_quote=span["text_verbatim"], source_start=span["start"], source_end=span["end"])
        elements.append(item)
    unmapped = [
        {
            "text_verbatim": unit["text_verbatim"],
            "source_start": unit["start"],
            "source_end": unit["end"],
            "reviewed": False,
        }
        for unit in snapshot["units"]
    ]
    return {
        "schema_version": "1.0.0",
        "source_text_sha256": snapshot["text_sha256"],
        "case_type": case_type,
        "case_type_human_confirmed": snapshot["classification"]["human_confirmed"],
        "claims": [
            {
                "order": item["order"],
                "text_verbatim": item["text_verbatim"],
                "source_start": item["start"],
                "source_end": item["end"],
                "sha256": item["sha256"],
                "target_field_ids": [],
            }
            for item in snapshot["claims"]
        ],
        "elements": elements,
        "unmapped_segments": unmapped,
        "blockers": [],
    }
