#!/usr/bin/env python3
"""Render contract-draft.json into a formal 建设工程施工合同 DOCX working draft.

Typography follows the skill contract render contract (2026-08):
  - Body font Noto Serif SC (思源宋体, SIL OFL); title 18pt REGULAR, centered
  - Body 14pt regular; labels bold inline
  - Fixed line spacing 25pt; first-line indent 28pt (2 chars)
  - Margins: left 25mm / right 20mm / top 30mm / bottom 20mm
  - Structure: 合同标题 → 甲方/乙方（当事人信息，〔占位〕保留）→ 鉴于条款（如有，
    不编号）→ 各条款按“第X条”编号（条款标题加粗，条内款项按 1. 2. 3. 编号）→
    签署栏（甲方/乙方盖章、法定代表人/委托代理人签字、签订日期〔占位〕）
  - Compact brand header/footer via cn-legal-core docx_brand
  - Refuses to overwrite an existing output file

Usage:
    python3 render_docx.py --input contract-draft.json --output <dir>/建设工程施工合同.docx
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

CN_LEGAL_CORE = Path(__file__).resolve().parent.parent.parent / "cn-legal-core"
BODY_FONT = "Noto Serif SC"  # 思源宋体 OFL，替代系统仿宋防侵权

CONTRACT_TITLE = "建设工程施工合同"
BRAND_TITLE = "建设工程施工合同"
BRAND_SUBJECT = "AI辅助生成，须由执业律师逐项核验"
AUTHOR = "AIOffice职场通关-excel1949"

ROLE_TO_SIDE = {"发包人": "甲方", "承包人": "乙方"}

MISSING_PARTY_FIELDS = "统一社会信用代码：〔占位〕；住所：〔占位〕；法定代表人：〔占位〕"


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


def add_clause_heading(doc: Document, text: str) -> None:
    """Clause heading 第X条 …: bold 14pt, flush left, fixed 25pt spacing."""
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(25)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    set_run_font(run, 14, bold=True)
    return paragraph


def add_item_para(doc: Document, number: int, text: str) -> None:
    """Numbered item inside a clause: 1. 2. 3. …, 28pt first-line indent."""
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(28)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(25)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(f"{number}. {text}")
    set_run_font(run, 14, bold=False)
    return paragraph


def add_spacer(doc: Document, height_pt: float = 25) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(height_pt)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    return paragraph


def remove_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "none")
        borders.append(element)
    tbl_pr.append(borders)


def format_table_cell(cell, text: str) -> None:
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(25)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    set_run_font(run, 14, bold=False)


def add_signature_block(doc: Document) -> None:
    """签署栏：甲方/乙方盖章处、法定代表人/委托代理人签字处、签订日期〔占位〕."""
    for _ in range(2):
        add_spacer(doc)
    table = doc.add_table(rows=4, cols=2)
    remove_table_borders(table)
    table.autofit = False
    left_col, right_col = table.columns[0], table.columns[1]
    for column in (left_col, right_col):
        column.width = Cm(8.0)
    rows = [
        ("甲方（盖章）：", "乙方（盖章）："),
        ("法定代表人（签字）：", "法定代表人（签字）："),
        ("委托代理人（签字）：", "委托代理人（签字）："),
        ("签订日期：＿＿＿＿年＿＿月＿＿日（〔占位〕）", "签订日期：＿＿＿＿年＿＿月＿＿日（〔占位〕）"),
    ]
    for row_index, (left_text, right_text) in enumerate(rows):
        left_cell = table.rows[row_index].cells[0]
        right_cell = table.rows[row_index].cells[1]
        left_cell.width = Cm(8.0)
        right_cell.width = Cm(8.0)
        format_table_cell(left_cell, left_text)
        format_table_cell(right_cell, right_text)


def render(draft: dict) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    parties = draft.get("parties", [])
    clauses = draft.get("clauses", [])

    # Title: 思源宋体 18pt REGULAR, centered (not bold)
    add_para(doc, CONTRACT_TITLE, size=18, bold=True, align="center")
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）

    # 甲方 / 乙方（当事人信息，〔占位〕保留）
    for index, party in enumerate(parties):
        role = party.get("role", "")
        name = party.get("name", "")
        side = ROLE_TO_SIDE.get(role) or ("甲方" if index == 0 else "乙方")
        add_label_para(doc, f"{side}（{role}）：", name)
        add_para(doc, MISSING_PARTY_FIELDS, first_indent=28)

    # 鉴于条款（如有）：heading 含“鉴于”的条款不编号，置于正文条款之前
    recital_clauses = [c for c in clauses if "鉴于" in c.get("heading", "")]
    numbered_clauses = [c for c in clauses if "鉴于" not in c.get("heading", "")]
    for recital in recital_clauses:
        add_clause_heading(doc, recital.get("heading", "鉴于"))
        for number, line in enumerate(recital.get("body_lines", []), 1):
            add_item_para(doc, number, line)

    # 各条款按“第X条”编号，条内款项按 1. 2. 3. 编号
    for clause_index, clause in enumerate(numbered_clauses, 1):
        add_clause_heading(doc, f"第{clause_index}条　{clause.get('heading', '')}")
        for number, line in enumerate(clause.get("body_lines", []), 1):
            add_item_para(doc, number, line)

    # 签署栏
    add_signature_block(doc)
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染《建设工程施工合同》DOCX 工作稿（律师审查用）")
    parser.add_argument("--input", type=Path, required=True, help="contract-draft.json 路径")
    parser.add_argument("--output", type=Path, required=True,
                        help="输出 docx 路径（默认建议文件名：建设工程施工合同.docx，不得覆盖已存在文件）")
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"拒绝覆盖已存在输出：{args.output}")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    draft = payload["draft"] if "draft" in payload else payload

    doc = render(draft)

    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py", "cn_legal_core_brand")
    with tempfile.TemporaryDirectory(prefix=".cn-contract-draft-docx-") as temporary:
        raw_path = Path(temporary) / "raw.docx"
        doc.save(raw_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            docx_brand.brand_docx(
                raw_path, args.output,
                title=BRAND_TITLE, subject=BRAND_SUBJECT,
                compact=True,
            )
        except Exception:
            if args.output.exists():
                args.output.unlink()
            raise

    sha256 = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "sha256": sha256,
        "author": AUTHOR,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
