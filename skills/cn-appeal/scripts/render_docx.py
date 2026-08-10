#!/usr/bin/env python3
"""Render appeal-review.json into a formal Civil Appeal Brief (民事上诉状) DOCX.

Typography follows the court-filing contract shared with cn-complaint
(2026-08 reference):
  - Entire document in Noto Serif SC (思源宋体, OFL); title "上诉状" 18pt
    REGULAR (not bold), centered
  - Labels (上诉人/被上诉人/原审法院与案号/案由/上诉请求/事实与理由) bold 14pt
    inline; body 14pt regular
  - Fixed line spacing 25pt; first-line indent 28pt (2 chars)
  - Margins: left 25mm / right 20mm / top 30mm / bottom 20mm
  - Structure: title → appellant → respondent → original court & case number
    → cause of action → appeal requests (Chinese numerals 一、二、) →
    facts & reasons → 此致 → appeal court (flush left) → 2 spacer paragraphs
    → 上诉人 (indent ~15 chars) → date in Chinese uppercase numerals
  - Compact brand header/footer (small header logo + brand name + page number)

Input contract (appeal-review.json from build_appeal_review.py):
  required:
    request_integrity[]              -> {request_id, verbatim_text, ...}; appeal
                                       requests rendered verbatim, numbered
                                       with Chinese numerals (fallback:
                                       source_record.appeal_requests)
    issue_audit                      -> {fact_dispute[], legal_application[],
                                       procedural_issue[]}; rendered under
                                       事实与理由 as review questions grouped by
                                       category — the renderer never rewrites
                                       them into argument prose
  optional (absent -> 〔占位〕, which is preserved as-is when present):
    appellant / respondent           -> party display text (name, address, etc.)
    original_court_case              -> e.g. "杭州市余杭区人民法院（2024）浙
                                       0110民初〔占位〕号"
    cause_of_action                  -> e.g. "建设工程施工合同纠纷"
    appeal_court                     -> court addressed after 此致
    signature_date                   -> ISO date (2025-01-08) or Chinese text
    facts_and_reasons                -> list of paragraph strings; when present
                                       and non-empty it overrides the
                                       issue_audit-derived 事实与理由

The renderer refuses to overwrite an existing output file, does not fabricate
parties, causes of action, case numbers or deadlines, and never signs or seals.

Usage:
    python3 render_docx.py --input appeal-review.json --output <dir>/上诉状.docx
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

CN_LEGAL_CORE = Path(__file__).resolve().parent.parent.parent / "cn-legal-core"
BODY_FONT = "Noto Serif SC"  # 思源宋体 OFL，替代系统仿宋防侵权
PLACEHOLDER = "〔占位〕"

CN_DIGITS = "一二三四五六七八九十"
DATE_CN_DIGITS = {"0": "〇", "1": "一", "2": "二", "3": "三", "4": "四",
                  "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
ISSUE_CATEGORIES = (
    ("fact_dispute", "事实争议"),
    ("legal_application", "法律适用"),
    ("procedural_issue", "程序问题"),
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_run_font(run, size_pt: int, bold: bool = False) -> None:
    run.font.name = BODY_FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    run.font.size = Pt(size_pt)
    run.font.bold = bold


def add_para(doc: Document, text: str, *, size: int = 14, bold: bool = False,
             align: str = "left", first_indent: float = 0.0) -> None:
    paragraph = doc.add_paragraph()
    if align == "center":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if first_indent:
        paragraph.paragraph_format.first_line_indent = Pt(first_indent)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(25)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    set_run_font(run, size, bold)
    return paragraph


def add_label_para(doc: Document, label: str, content: str) -> None:
    """Label bold inline, content regular, same paragraph (2-char first-line indent)."""
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(28)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(25)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    label_run = paragraph.add_run(label)
    set_run_font(label_run, 14, bold=True)
    content_run = paragraph.add_run(content)
    set_run_font(content_run, 14, bold=False)
    return paragraph


def cn_number(n: int) -> str:
    """1 -> 一, 12 -> 十二, 21 -> 二十一 (Chinese numeral for lists)."""
    if n <= 10:
        return CN_DIGITS[n - 1]
    tens, ones = divmod(n, 10)
    tens_char = CN_DIGITS[tens - 1] if tens > 1 else ""
    return f"{tens_char}十" + (CN_DIGITS[ones - 1] if ones else "")


def cn_date(text: str) -> str:
    """'2025-01-08' -> '二〇二五年一月八日'; non-date strings pass through."""
    parts = text.strip().split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return text
    year, month, day = parts

    def to_cn(digits: str) -> str:
        return "".join(DATE_CN_DIGITS[d] for d in digits)

    return f"{to_cn(year)}年{to_cn(month).lstrip('〇') or '〇'}月{to_cn(day).lstrip('〇') or '〇'}日"


def request_texts(appeal: dict) -> list[str]:
    requests = appeal.get("request_integrity") or appeal.get("source_record", {}).get("appeal_requests", [])
    return [item.get("verbatim_text", "").strip() for item in requests if item.get("verbatim_text")]


def facts_and_reasons_paragraphs(appeal: dict) -> list[tuple[str, bool]]:
    """Return [(text, is_heading)] for the 事实与理由 section.

    Explicit facts_and_reasons (list of strings) wins; otherwise derive from
    issue_audit review questions grouped by category — questions are rendered
    verbatim, never rewritten into argument prose.
    """
    explicit = appeal.get("facts_and_reasons", [])
    if explicit:
        return [(str(item).strip(), False) for item in explicit if str(item).strip()]

    issue_audit = appeal.get("issue_audit") or {}
    paragraphs: list[tuple[str, bool]] = []
    for index, (category, label) in enumerate(ISSUE_CATEGORIES, 1):
        issues = issue_audit.get(category, [])
        if not issues:
            continue
        paragraphs.append((f"{cn_number(index)}、{label}", True))
        for number, issue in enumerate(issues, 1):
            question = str(issue.get("question", "")).strip()
            if question:
                paragraphs.append((f"（{cn_number(number)}）{question}", False))
    return paragraphs


def render(appeal: dict) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    appellant = str(appeal.get("appellant") or PLACEHOLDER)
    respondent = str(appeal.get("respondent") or PLACEHOLDER)
    original_court_case = str(appeal.get("original_court_case") or PLACEHOLDER)
    cause_of_action = str(appeal.get("cause_of_action") or PLACEHOLDER)
    appeal_court = str(appeal.get("appeal_court") or PLACEHOLDER)
    signature_date = str(appeal.get("signature_date") or "")

    # Title: 思源宋体 18pt REGULAR, centered (not bold)
    add_para(doc, "上诉状", size=18, bold=True, align="center")
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）

    # Parties, original court & case number, cause of action
    add_label_para(doc, "上诉人：", appellant)
    add_label_para(doc, "被上诉人：", respondent)
    add_label_para(doc, "原审法院与案号：", original_court_case)
    add_label_para(doc, "案由：", cause_of_action)

    # Appeal requests (Chinese numerals 一、二、...), verbatim
    add_label_para(doc, "上诉请求：", "")
    for index, text in enumerate(request_texts(appeal), 1):
        add_para(doc, f"{cn_number(index)}、{text}", first_indent=28)

    # Facts & reasons
    add_label_para(doc, "事实与理由：", "")
    for text, is_heading in facts_and_reasons_paragraphs(appeal):
        add_para(doc, text, first_indent=28, bold=is_heading)

    # Closing
    add_para(doc, "此致", first_indent=28)
    add_para(doc, appeal_court)  # flush left, no indent

    # Two spacer paragraphs (with first-line indent)
    for _ in range(2):
        add_para(doc, "", first_indent=28)

    # Signature block: 上诉人 indented ~15 chars, date with Chinese numerals
    add_para(doc, f"上诉人：{appellant}", first_indent=210)
    if signature_date:
        add_para(doc, f"{cn_date(signature_date)}", first_indent=140)
    else:
        add_para(doc, "＿＿＿＿年＿＿月＿＿日", first_indent=140)

    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染民事上诉状 DOCX（法院参考排版）")
    parser.add_argument("--input", type=Path, required=True, help="appeal-review.json 路径")
    parser.add_argument("--output", type=Path, required=True, help="输出 docx 路径（不得已存在）")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    payload = data.get("appeal") or data.get("appeal_review") or data

    doc = render(payload)
    if args.output.exists():
        raise FileExistsError(f"拒绝覆盖：{args.output}")

    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py", "cn_legal_core_brand")
    with tempfile.TemporaryDirectory(prefix=".cn-appeal-docx-") as temporary:
        raw_path = Path(temporary) / "raw.docx"
        doc.save(raw_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            docx_brand.brand_docx(
                raw_path, args.output,
                title="上诉状", subject="AI辅助生成，须由执业律师逐项核验",
                compact=True,
            )
        except Exception:
            if args.output.exists():
                args.output.unlink()
            raise
    print(json.dumps({"ok": True, "output": str(args.output), "author": "AIOffice职场通关-excel1949"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
