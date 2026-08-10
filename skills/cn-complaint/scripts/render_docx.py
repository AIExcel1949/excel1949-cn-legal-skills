#!/usr/bin/env python3
"""Render complaint.json into a formal Civil Complaint (民事起诉状) DOCX.

Typography follows the civil-prosecution-brief court-filing contract
(user-authored reference contract, 2026-08):
  - Entire document in FangSong (仿宋); title 18pt REGULAR (not bold), centered
  - Labels (原告/被告/案由/诉讼请求/事实与理由) bold 14pt inline; body 14pt regular
  - Fixed line spacing 25pt; first-line indent 28pt (2 chars)
  - Margins: left 25mm / right 20mm / top 30mm / bottom 20mm
  - Structure: title → plaintiff → defendant → cause of action → claims
    (Chinese numerals 一、二、) → facts & reasons (continuous narrative) →
    此致 → court (flush left) → 2 spacer paragraphs → 具状人 (indent ~15 chars)
    → date in Chinese uppercase numerals (二〇二二年三月二十一日)
  - Compact brand header/footer (small header logo + brand name + page number)

Usage:
    python3 render_docx.py --input complaint.json --output <dir>/民事起诉状.docx
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

CN_DIGITS = "一二三四五六七八九十"
DATE_CN_DIGITS = {"0": "〇", "1": "一", "2": "二", "3": "三", "4": "四",
                  "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}


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
    """1 -> 一, 12 -> 十二, 21 -> 二十一 (Chinese numeral for claim lists)."""
    if n <= 10:
        return CN_DIGITS[n - 1]
    tens, ones = divmod(n, 10)
    tens_char = CN_DIGITS[tens - 1] if tens > 1 else ""
    return f"{tens_char}十" + (CN_DIGITS[ones - 1] if ones else "")


def cn_date(text: str) -> str:
    """'2022-03-21' -> '二〇二二年三月二十一日'; non-date strings pass through."""
    parts = text.strip().split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return text
    year, month, day = parts
    def to_cn(digits: str) -> str:
        return "".join(DATE_CN_DIGITS[d] for d in digits)
    return f"{to_cn(year)}年{to_cn(month).lstrip('〇') or '〇'}月{to_cn(day).lstrip('〇') or '〇'}日"


def render(complaint: dict) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    case_type = complaint.get("case_type", {}).get("text", "")
    parties = complaint.get("parties", [])
    claims = complaint.get("claims", [])
    facts = complaint.get("facts", [])
    grounds = complaint.get("legal_grounds", [])
    court = complaint.get("court", {}).get("text", "")
    as_of = complaint.get("as_of_date", "")

    # Title: 仿宋 18pt REGULAR, centered (not bold)
    add_para(doc, "民事起诉状", size=18, bold=True, align="center")
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）

    # Parties
    for party in parties:
        role = party.get("role", "")
        label = {"plaintiff": "原告", "defendant": "被告", "third_party": "第三人"}.get(role, role)
        add_label_para(doc, f"{label}：", party.get("display_text", ""))

    # Cause of action
    if case_type:
        add_label_para(doc, "案由：", case_type)

    # Claims (Chinese numerals 一、二、...)
    add_label_para(doc, "诉讼请求：", "")
    for index, claim in enumerate(claims, 1):
        add_para(doc, f"{cn_number(index)}、{claim.get('text_verbatim', '')}", first_indent=28)

    # Facts & Reasons: continuous narrative paragraphs, no sub-headings
    add_label_para(doc, "事实与理由：", "")
    for fact in facts:
        add_para(doc, fact.get("text", ""), first_indent=28)
    for ground in grounds:
        add_para(doc, ground.get("text", ""), first_indent=28)

    # Closing
    add_para(doc, "此致", first_indent=28)
    if court:
        add_para(doc, court)  # flush left, no indent

    # Two spacer paragraphs (with first-line indent)
    for _ in range(2):
        add_para(doc, "", first_indent=28)

    # Signature block: 具状人 indented ~15 chars, date with Chinese numerals
    add_para(doc, "具状人：", first_indent=210)
    if as_of:
        add_para(doc, f"{cn_date(as_of)}", first_indent=140)
    else:
        add_para(doc, "＿＿＿＿年＿＿月＿＿日", first_indent=140)

    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染民事起诉状 DOCX（法院参考排版）")
    parser.add_argument("--input", type=Path, required=True, help="complaint.json 路径")
    parser.add_argument("--output", type=Path, required=True, help="输出 docx 路径（不得已存在）")
    args = parser.parse_args()

    complaint = json.loads(args.input.read_text(encoding="utf-8"))
    payload = complaint["complaint"] if "complaint" in complaint else complaint
    payload["as_of_date"] = payload.get("as_of_date", "") or complaint.get("as_of_date", "")

    doc = render(payload)
    if args.output.exists():
        raise FileExistsError(f"拒绝覆盖：{args.output}")

    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py", "cn_legal_core_brand")
    with tempfile.TemporaryDirectory(prefix=".cn-complaint-docx-") as temporary:
        raw_path = Path(temporary) / "raw.docx"
        doc.save(raw_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            docx_brand.brand_docx(
                raw_path, args.output,
                title="民事起诉状", subject="AI辅助生成，须由执业律师逐项核验",
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
