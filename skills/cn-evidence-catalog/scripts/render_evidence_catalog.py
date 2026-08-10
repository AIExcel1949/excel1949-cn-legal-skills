#!/usr/bin/env python3
"""Render an evidence catalog (证据目录) DOCX per the evidence-catalog-docx contract
(user-authored reference contract, 2026-08):

  - Margins: top 2.5 / bottom 2.0 / left 2.5 / right 2.0 cm, A4 portrait
  - Case title centered (line spacing 2.0); main heading "证 据 目 录" in 黑体
    18pt NOT bold, centered, with a space between each character
  - Meta block: 提交人（角色）：提交人 (label bold) / 提交时间：YYYY年M月D日 (label bold)
  - One blank separator paragraph (exact 10pt line spacing)
  - Evidence items: "证据一、" + title (ENTIRE line bold, Chinese numeral + 顿号);
    "证明目的：" (label bold) + regular content
  - Body in 仿宋; exact 26pt line spacing; paragraph before/after 156 twips
  - Footer: cluster brand page number (第 N 页) via cn-legal-core compact branding
  - No header, no tables, no images in body

Usage:
    python3 render_evidence_catalog.py --input catalog.json --output <dir>/证据目录.docx
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

CN_LEGAL_CORE = Path(__file__).resolve().parent.parent.parent / "cn-legal-core"
BODY_FONT = "Noto Serif CJK SC"  # 思源宋体 OFL（与旧版交付稿一致）
HEADING_FONT = "Noto Serif CJK SC"  # 标题同字体加粗（旧版交付稿样式）

CN_NUMERALS = "一二三四五六七八九十"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_run_font(run, font: str, size_pt: int, bold: bool = False) -> None:
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    run.font.size = Pt(size_pt)
    run.font.bold = bold


def cn_number(n: int) -> str:
    if n <= 10:
        return CN_NUMERALS[n - 1]
    tens, ones = divmod(n, 10)
    tens_char = CN_NUMERALS[tens - 1] if tens > 1 else ""
    return f"{tens_char}十" + (CN_NUMERALS[ones - 1] if ones else "")


def add_body_para(doc: Document, text: str, *, bold: bool = False) -> None:
    """Body paragraph: FangSong 14pt, exact 26pt line spacing, before/after 156 twips."""
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(26)
    paragraph.paragraph_format.space_before = Pt(7.8)   # 156 twips
    paragraph.paragraph_format.space_after = Pt(7.8)    # 156 twips
    run = paragraph.add_run(text)
    set_run_font(run, BODY_FONT, 14, bold)
    return paragraph






def build_table(doc, headers, rows, col_widths_twips):
    """表格版优化（2026-08-10）：列宽按内容分配、表头加粗、单元格垂直居中、12pt。"""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for col, width in zip(table.columns, col_widths_twips):
        col.width = Pt(width * 0.05)  # 缇→pt（1pt=20缇）
    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(cell.paragraphs[0].add_run(h), BODY_FONT, 12, bold=True)
    for i, row in enumerate(rows, 1):
        for j, val in enumerate(row):
            cell = table.rows[i].cells[j]
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER if j in (0, len(headers) - 2, len(headers) - 1) else WD_ALIGN_PARAGRAPH.LEFT
            set_run_font(cell.paragraphs[0].add_run(val), BODY_FONT, 12, bold=False)
    return table

def render_list(data: dict) -> Document:
    """格式一：证据清单-横列式（6 列：序号/证据名称/证据来源/证明内容/原件复印件/页数，无当事人头部）。"""
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0); section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5); section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5); section.right_margin = Cm(2.0)

    title = doc.add_paragraph(); title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("证 据 清 单"); set_run_font(r, HEADING_FONT, 22, bold=True)
    meta = doc.add_paragraph()
    r = meta.add_run(f"提交人（{data.get('submitter_role', '')}）：{data.get('submitter', '')}   提交时间：{data.get('submit_date', '')}")
    set_run_font(r, BODY_FONT, 11, bold=False)

    headers = ("序号", "证据名称", "证据来源", "证明内容", "原件复印件", "页数")
    rows = []
    for i, item in enumerate(data.get("items", []), 1):
        rows.append((str(i), item.get("title", ""), item.get("source", ""),
                     item.get("proof_purpose", ""), item.get("form", ""), item.get("pages", "")))
    build_table(doc, headers, rows, [800, 2800, 1800, 2150, 900, 900])
    return doc


def render_directory(data: dict) -> Document:
    """格式二：证据目录-标准竖表（7 列，含案由/当事人头部，法院提交首选）。"""
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0); section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5); section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5); section.right_margin = Cm(2.0)

    title = doc.add_paragraph(); title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("证 据 目 录"); set_run_font(r, HEADING_FONT, 22, bold=True)

    for line in ("案由：{case_cause}", "原告（申请人）：{plaintiff}", "被告（被申请人）：{defendant}", "提交日期：{submit_date}"):
        para = doc.add_paragraph()
        r = para.add_run(line.format(**{k: data.get(k, "") for k in ("case_cause", "plaintiff", "defendant", "submit_date")}))
        set_run_font(r, BODY_FONT, 11, bold=False)

    headers = ("序号", "证据名称", "证据来源", "证明目的", "证据形式", "页数", "备注")
    rows = []
    for i, item in enumerate(data.get("items", []), 1):
        rows.append((str(i), item.get("title", ""), item.get("source", ""),
                     item.get("proof_purpose", ""), item.get("form", ""), item.get("pages", ""), item.get("notes", "")))
    build_table(doc, headers, rows, [800, 2600, 1600, 2250, 800, 800, 500])
    if data.get("volume_note"):
        para = doc.add_paragraph()
        r = para.add_run(f"说明：{data['volume_note']}")
        set_run_font(r, BODY_FONT, 11, bold=False)
    return doc

def render(data: dict) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    # 1. Case title, centered, line spacing 2.0
    case_para = doc.add_paragraph()
    case_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    case_para.paragraph_format.line_spacing = 2.0
    run = case_para.add_run(data.get("case_title", ""))
    set_run_font(run, BODY_FONT, 11, bold=False)

    # 2. Main heading: 证 据 目 录 (黑体 18pt NOT bold, spaces between chars)
    heading_para = doc.add_paragraph()
    heading_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading_para.paragraph_format.line_spacing = 1.5
    run = heading_para.add_run("证 据 目 录")
    set_run_font(run, HEADING_FONT, 22, bold=True)

    # 3. Meta block: labels bold inline
    meta1 = doc.add_paragraph()
    meta1.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    meta1.paragraph_format.line_spacing = Pt(26)
    label = meta1.add_run(f"提交人（{data.get('submitter_role', '')}）：")
    set_run_font(label, BODY_FONT, 12, bold=False)
    value = meta1.add_run(data.get("submitter", ""))
    set_run_font(value, BODY_FONT, 12, bold=False)

    meta2 = doc.add_paragraph()
    meta2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    meta2.paragraph_format.line_spacing = Pt(26)
    label = meta2.add_run("提交时间：")
    set_run_font(label, BODY_FONT, 12, bold=False)
    value = meta2.add_run(data.get("submit_date", ""))
    set_run_font(value, BODY_FONT, 12, bold=False)

    # 4. Empty separator paragraph (exact 10pt line spacing, no before/after)
    separator = doc.add_paragraph()
    separator.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    separator.paragraph_format.line_spacing = Pt(10)
    separator.paragraph_format.space_before = Pt(0)
    separator.paragraph_format.space_after = Pt(0)

    # 5. Evidence items: 证据一、title (bold) + 证明目的：content (label bold)
    for index, item in enumerate(data.get("items", []), 1):
        heading = doc.add_paragraph()
        heading.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        heading.paragraph_format.line_spacing = Pt(26)
        heading.paragraph_format.space_before = Pt(7.8)
        heading.paragraph_format.space_after = Pt(7.8)
        run = heading.add_run(f"证据{cn_number(index)}、{item.get('title', '')}")
        set_run_font(run, BODY_FONT, 12, bold=True)

        purpose = doc.add_paragraph()
        purpose.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        purpose.paragraph_format.line_spacing = Pt(26)
        purpose.paragraph_format.space_before = Pt(7.8)
        purpose.paragraph_format.space_after = Pt(7.8)
        label = purpose.add_run("证明目的：")
        set_run_font(label, BODY_FONT, 12, bold=False)
        value = purpose.add_run(item.get("proof_purpose", ""))
        set_run_font(value, BODY_FONT, 12, bold=False)

    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染证据目录 DOCX（3 格式，BUG-009/010）")
    parser.add_argument("--input", type=Path, required=True, help="evidence-catalog-input.json 路径")
    parser.add_argument("--output", type=Path, required=True, help="输出目录（必须不存在或为空）")
    parser.add_argument("--format", action="append", default=[], choices=["list", "directory", "narrative"],
                        help="证据目录格式，可重复指定；缺省三种全量生成")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    formats = args.format or ["list", "directory", "narrative"]
    output_dir = args.output
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"输出目录必须不存在或为空：{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py", "cn_legal_core_brand")
    names = {"list": "证据清单", "directory": "证据目录", "narrative": "证据目录-叙述式"}
    outputs = []
    for fmt in formats:
        doc = {"list": render_list, "directory": render_directory, "narrative": render}[fmt](data)
        target = output_dir / f"{names[fmt]}.docx"
        with tempfile.TemporaryDirectory(prefix=".cn-evidence-catalog-") as temporary:
            raw_path = Path(temporary) / "raw.docx"
            doc.save(raw_path)
            docx_brand.brand_docx(raw_path, target, title=names[fmt], subject="AI辅助生成，须由执业律师逐项核验", compact=True)
        outputs.append(str(target))
        print(f"已生成：{target}")
    print(json.dumps({"ok": True, "outputs": outputs, "author": "AIOffice职场通关-excel1949"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
