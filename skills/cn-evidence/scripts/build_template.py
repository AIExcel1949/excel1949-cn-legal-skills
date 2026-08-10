#!/usr/bin/env python3
"""生成 AIOffice 录音文字稿 DOCX 模板。

用法：
    python3 scripts/build_template.py
    python3 scripts/build_template.py --output /path/to/模板.docx
"""

from __future__ import annotations

import argparse
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = SKILL_ROOT / "assets" / "录音文字稿-模板.docx"
DEFAULT_LOGO = SKILL_ROOT / "assets" / "brand" / "header-logo.png"
DEFAULT_FOOTER_LOGO = SKILL_ROOT / "assets" / "brand" / "footer-logo.png"
FONT_NAME = "Source Han Sans CN"
BRAND_GREEN = "1F8A4F"
DEEP_GREEN = "0F5A33"
LIGHT_GREEN = "F5F9F6"
TEXT_DARK = "1F1F1F"
TEXT_MUTED = "6B6B6B"
DOCUMENT_AUTHOR = "AIOffice职场通关-excel1949"


def _set_cell_shading(cell, fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.insert_element_before(
            shading,
            "w:noWrap",
            "w:tcMar",
            "w:textDirection",
            "w:tcFitText",
            "w:vAlign",
            "w:hideMark",
            "w:headers",
            "w:cellIns",
            "w:cellDel",
            "w:cellMerge",
            "w:tcPrChange",
        )
    shading.set(qn("w:fill"), fill)
    shading.set(qn("w:val"), "clear")


def _set_cell_margins(cell, *, top=90, start=120, bottom=90, end=120) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.insert_element_before(
            tc_mar,
            "w:textDirection",
            "w:tcFitText",
            "w:vAlign",
            "w:hideMark",
            "w:headers",
            "w:cellIns",
            "w:cellDel",
            "w:cellMerge",
            "w:tcPrChange",
        )
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _set_table_borders(table, color: str = "D9E6DE", size: str = "4") -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.insert_element_before(
            borders,
            "w:shd",
            "w:tblLayout",
            "w:tblCellMar",
            "w:tblLook",
            "w:tblCaption",
            "w:tblDescription",
            "w:tblPrChange",
        )
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), size)
        node.set(qn("w:color"), color)


def _set_run_font(run, size_pt: float, *, bold: bool = False, color: str = TEXT_DARK) -> None:
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    run.font.name = FONT_NAME
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT_NAME)
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _add_page_number(paragraph) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run = paragraph.add_run("第 ")
    _set_run_font(run, 8.5, color=TEXT_MUTED)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    paragraph._p.append(field)
    run = paragraph.add_run(" 页")
    _set_run_font(run, 8.5, color=TEXT_MUTED)


def _clear_story(story) -> None:
    element = story._element
    for child in list(element):
        element.remove(child)


def add_brand_header_and_footer(
    doc,
    logo_path: Path = DEFAULT_LOGO,
    footer_logo_path: Path = DEFAULT_FOOTER_LOGO,
) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm

    for section in doc.sections:
        header = section.header
        _clear_story(header)
        paragraph = header.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.space_after = Cm(0.12)
        if logo_path.exists():
            paragraph.add_run().add_picture(str(logo_path), width=Cm(3.85))
        p_pr = paragraph._p.get_or_add_pPr()
        p_bdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "8")
        bottom.set(qn("w:space"), "3")
        bottom.set(qn("w:color"), BRAND_GREEN)
        p_bdr.append(bottom)
        p_pr.insert_element_before(
            p_bdr,
            "w:shd",
            "w:tabs",
            "w:suppressAutoHyphens",
            "w:kinsoku",
            "w:wordWrap",
            "w:overflowPunct",
            "w:topLinePunct",
            "w:autoSpaceDE",
            "w:autoSpaceDN",
            "w:bidi",
            "w:adjustRightInd",
            "w:snapToGrid",
            "w:spacing",
            "w:ind",
            "w:contextualSpacing",
            "w:mirrorIndents",
            "w:suppressOverlap",
            "w:jc",
            "w:textDirection",
            "w:textAlignment",
            "w:textboxTightWrap",
            "w:outlineLvl",
            "w:divId",
            "w:cnfStyle",
            "w:rPr",
            "w:sectPr",
            "w:pPrChange",
        )

        footer = section.footer
        _clear_story(footer)
        footer_p = footer.add_paragraph()
        footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if footer_logo_path.exists():
            footer_p.add_run().add_picture(str(footer_logo_path), width=Cm(1.6))
        brand = footer_p.add_run("  AIOffice职场通关  ·  ")
        _set_run_font(brand, 8.5, color=BRAND_GREEN)
        _add_page_number(footer_p)


def _add_section_heading(doc, text: str) -> None:
    from docx.shared import Pt

    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(5)
    run = paragraph.add_run(text)
    _set_run_font(run, 14, bold=True, color=DEEP_GREEN)


def _add_body_line(doc, text: str, *, muted: bool = False) -> None:
    from docx.shared import Pt

    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.line_spacing = 1.35
    run = paragraph.add_run(text)
    _set_run_font(run, 11, color=TEXT_MUTED if muted else TEXT_DARK)


def build_template(
    output_path: Path,
    logo_path: Path = DEFAULT_LOGO,
    footer_logo_path: Path = DEFAULT_FOOTER_LOGO,
) -> Path:
    from docx import Document
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    doc = Document()
    doc.core_properties.author = DOCUMENT_AUTHOR
    doc.core_properties.last_modified_by = DOCUMENT_AUTHOR
    doc.core_properties.title = "录音文字稿模板"
    doc.core_properties.subject = "中国民商事录音证据转写"
    doc.core_properties.category = "AIOffice职场通关法律Skill"
    doc.core_properties.comments = "AI辅助生成，须由执业律师逐项核验"
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    section.header_distance = Cm(0.65)
    section.footer_distance = Cm(0.8)

    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
    normal.font.size = Pt(11)

    zoom = doc.settings._element.find(qn("w:zoom"))
    if zoom is not None and zoom.get(qn("w:percent")) is None:
        zoom.set(qn("w:percent"), "100")

    add_brand_header_and_footer(doc, logo_path, footer_logo_path)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(8)
    title.paragraph_format.space_after = Pt(12)
    _set_run_font(title.add_run("录音文字稿"), 20, bold=True, color=TEXT_DARK)

    _add_section_heading(doc, "一、录音基本信息")
    rows = [
        ("原始录音文件", "【待填写】"),
        ("录音时间", "【待填写；无法确认时如实注明】"),
        ("录音方式与时长", "【待填写】"),
        ("说话人对应", "SPEAKER_0＝【待确认】；SPEAKER_1＝【待确认】"),
        ("SHA-256", "【原始文件哈希值】"),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Cm(3.6)
    table.columns[1].width = Cm(12.4)
    _set_table_borders(table)
    for index, (label, value) in enumerate(rows):
        left, right = table.rows[index].cells
        left.width = Cm(3.6)
        right.width = Cm(12.4)
        left.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_cell_margins(left)
        _set_cell_margins(right)
        _set_cell_shading(left, LIGHT_GREEN)
        _set_run_font(left.paragraphs[0].add_run(label), 10, bold=True, color=DEEP_GREEN)
        _set_run_font(right.paragraphs[0].add_run(value), 10, color=TEXT_DARK)

    _add_section_heading(doc, "二、文字稿正文")
    _add_body_line(doc, "说明：说话人标签是声纹聚类结果，不等于身份识别，必须由人工确认对应关系。", muted=True)
    _add_body_line(doc, "[00:00] SPEAKER_0：【转写内容】")
    _add_body_line(doc, "[00:05] SPEAKER_1：【转写内容】")
    _add_body_line(doc, "（——录音结束，总时长【待填写】——）", muted=True)

    _add_section_heading(doc, "三、校核说明")
    _add_body_line(
        doc,
        "本稿系原始录音的辅助文字索引，不替代原始录音；如文字与原始录音不一致，以原始录音为准。听不清、低置信度或说话人存疑之处，须逐句回听确认。",
    )
    _add_body_line(doc, "校核状态：□ 未完成逐句回听　　□ 已完成逐句回听")
    _add_body_line(doc, "整理人：【待填写】　　校核人：【待填写】　　日期：【待填写】")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 AIOffice 录音文字稿 DOCX 模板")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--logo", type=Path, default=DEFAULT_LOGO)
    parser.add_argument("--footer-logo", type=Path, default=DEFAULT_FOOTER_LOGO)
    args = parser.parse_args()
    output = build_template(args.output, args.logo, args.footer_logo)
    print(f"已生成：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
