#!/usr/bin/env python3
"""生成独立的要素式转换核验稿并回读校验。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from common import ASSET_DIR, AUTHOR, GENERATOR_VERSION, ConversionError, dump_json, field_catalog, sha256_bytes
from validate_mapping import validate_mapping


BODY_FONT = "Noto Serif CJK SC"
HEADING_FONT = "Noto Sans CJK SC"
TEXT_COLOR = RGBColor(31, 31, 31)
SECONDARY_COLOR = RGBColor(107, 107, 107)
GREEN = "1F8A4F"


def set_cell_shading(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def set_run_font(run, name: str, size: float, bold: bool = False, color: RGBColor = TEXT_COLOR) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)


def add_text(paragraph, value: str, *, name: str = BODY_FONT, size: float = 10.5, bold: bool = False, color: RGBColor = TEXT_COLOR):
    run = paragraph.add_run(value)
    set_run_font(run, name, size, bold, color)
    return run


def set_document_defaults(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.3)
    section.right_margin = Cm(2.3)
    section.header_distance = Cm(1.2)
    section.footer_distance = Cm(1.2)
    normal = document.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), BODY_FONT)


def add_heading(document: Document, value: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(6)
    add_text(paragraph, value, name=HEADING_FONT, size=12, bold=True)


def add_element_table(document: Document, rows: list[dict]) -> None:
    table = document.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    table.autofit = False
    table.columns[0].width = Cm(5.2)
    table.columns[1].width = Cm(11.2)
    header = table.rows[0].cells
    header_properties = table.rows[0]._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    header_properties.append(repeat)
    header[0].text = "要素"
    header[1].text = "原文转换内容"
    for cell in header:
        set_cell_shading(cell, "F5F9F6")
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                set_run_font(run, HEADING_FONT, 10.5, True)
    for item in rows:
        cells = table.add_row().cells
        cells[0].text = ""
        cells[1].text = ""
        add_text(cells[0].paragraphs[0], item["label"], name=HEADING_FONT, size=10)
        value = item["value"] if item["status"] == "provided" else ""
        add_text(cells[1].paragraphs[0], value, size=10)
        for cell in cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP


def group_elements(mapping: dict) -> list[tuple[str, list[dict]]]:
    groups: list[tuple[str, list[dict]]] = []
    current_section = None
    current_items: list[dict] = []
    skip = {"claim.fulltext", "fact.fulltext", "signature.person", "signature.date"}
    for item in mapping["elements"]:
        if item["field_id"] in skip:
            continue
        if item["section"] != current_section:
            if current_items:
                groups.append((current_section, current_items))
            current_section = item["section"]
            current_items = []
        current_items.append(item)
    if current_items:
        groups.append((current_section, current_items))
    return groups


def build_document(snapshot: dict, mapping: dict, report: dict, destination: Path) -> None:
    document = Document()
    set_document_defaults(document)
    core = document.core_properties
    core.author = AUTHOR
    core.last_modified_by = AUTHOR
    core.title = "要素式民事起诉状转换核验稿"
    core.subject = "传统叙述式民事起诉状转换为要素式结构"
    core.category = "AIOffice职场通关法律Skill"
    core.comments = "仅供律师核验，不得直接提交。"

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(4)
    add_text(title, "民事起诉状", name=HEADING_FONT, size=18, bold=True)
    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(10)
    add_text(subtitle, f"（{report['case_label']}·要素式转换核验稿）", name=HEADING_FONT, size=12, bold=True)

    notice = document.add_paragraph()
    notice.paragraph_format.space_after = Pt(10)
    add_text(
        notice,
        "提示：本稿由传统诉状原文转换生成，不是最高人民法院原版表格。原文缺失项保持空白，所有内容须由执业律师对照法〔2025〕82号及受理法院要求逐项核验。",
        name=HEADING_FONT,
        size=9,
        color=SECONDARY_COLOR,
    )

    add_heading(document, "诉讼请求（保持原文顺序与文字）")
    for item in mapping["claims"]:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.3)
        paragraph.paragraph_format.first_line_indent = Cm(-0.3)
        add_text(paragraph, f"{item['order']}．{item['text_verbatim']}", size=10.5)

    facts_item = next(item for item in mapping["elements"] if item["field_id"] == "fact.fulltext")
    add_heading(document, "事实与理由（保持原文）")
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Cm(0.74)
    paragraph.paragraph_format.line_spacing = 1.5
    add_text(paragraph, facts_item["value"], size=10.5)

    for section, items in group_elements(mapping):
        add_heading(document, section)
        add_element_table(document, items)

    if report["uncovered_segments"]:
        document.add_section(WD_SECTION.NEW_PAGE)
        add_heading(document, "原文保全附页（未归入专属要素）")
        explanation = document.add_paragraph()
        add_text(explanation, "以下内容按原文保留，避免格式转换造成静默遗漏；承办律师应决定是否转录至官方表格的补充栏或另附页。", size=9, color=SECONDARY_COLOR)
        for item in report["uncovered_segments"]:
            paragraph = document.add_paragraph(style=None)
            add_text(paragraph, item["text_verbatim"], size=10)

    document.add_paragraph()
    signature = document.add_paragraph()
    signature.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    add_text(signature, "具状人（签字、盖章）：________________", size=10.5)
    date = document.add_paragraph()
    date.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    add_text(date, "日期：_______年____月____日", size=10.5)
    source_note = document.add_paragraph()
    source_note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(source_note, f"源文本 SHA-256：{snapshot['text_sha256'][:16]}…｜仅供律师核验", name=HEADING_FONT, size=8, color=SECONDARY_COLOR)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw_path = destination.with_name(f".{destination.stem}.unbranded.docx")
    document.save(raw_path)
    core_script = Path(__file__).resolve().parent.parent.parent / "cn-legal-core" / "scripts" / "docx_brand.py"
    if not core_script.is_file():
        raw_path.unlink(missing_ok=True)
        raise ConversionError("缺少 cn-legal-core DOCX 品牌组件")
    try:
        subprocess.run(
            [
                sys.executable,
                str(core_script),
                str(raw_path),
                str(destination),
                "--title",
                "要素式民事起诉状转换核验稿",
                "--subject",
                "传统叙述式民事起诉状转换为要素式结构",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ConversionError(f"DOCX 品牌化失败：{exc.stderr.strip()}") from exc
    finally:
        raw_path.unlink(missing_ok=True)


def verify_document(path: Path, snapshot: dict, mapping: dict) -> list[str]:
    errors: list[str] = []
    document = Document(path)
    core = document.core_properties
    if core.author != AUTHOR or core.last_modified_by != AUTHOR:
        errors.append("DOCX 作者或最后修改者不正确")
    audit_script = Path(__file__).resolve().parent.parent.parent / "cn-legal-core" / "scripts" / "audit_docx.py"
    completed = subprocess.run(
        [sys.executable, str(audit_script), str(path)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        errors.append("DOCX 品牌或 OOXML 审计未通过")
    all_text = "\n".join(
        [paragraph.text for paragraph in document.paragraphs]
        + [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    )
    for item in mapping["claims"]:
        if item["text_verbatim"] not in all_text:
            errors.append(f"DOCX 回读未找到诉讼请求第 {item['order']} 项")
    facts = snapshot["sections"]["facts"]["text_verbatim"]
    if facts not in all_text:
        errors.append("DOCX 回读未找到完整事实与理由原文")
    for item in mapping["elements"]:
        if item["status"] == "provided" and item["field_id"] not in {"claim.fulltext", "fact.fulltext", "signature.person", "signature.date"}:
            if item["value"] not in all_text:
                errors.append(f"DOCX 回读未找到已映射要素：{item['field_id']}")
    if "原文未提供" in all_text:
        errors.append("DOCX 不得把缺失提示写入法院内容栏")
    return errors


def build_output(snapshot: dict, mapping: dict, output_dir: Path) -> dict:
    if output_dir.exists():
        raise ConversionError(f"为防止覆盖，输出目录必须不存在：{output_dir}")
    report = validate_mapping(snapshot, mapping, require_final=True)
    if not report["valid"]:
        raise ConversionError("\n".join(report["errors"]))
    case_spec, _ = field_catalog(mapping["case_type"])
    reference_template = ASSET_DIR / case_spec["template"]
    if not reference_template.is_file():
        raise ConversionError(f"缺少官方参考模板：{reference_template}")
    template_hash = sha256_bytes(reference_template.read_bytes())
    if template_hash != case_spec["template_sha256"]:
        raise ConversionError("官方参考模板哈希不在白名单内")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        docx_path = staging / "要素式民事起诉状-转换核验稿.docx"
        build_document(snapshot, mapping, report, docx_path)
        readback_errors = verify_document(docx_path, snapshot, mapping)
        if readback_errors:
            raise ConversionError("\n".join(readback_errors))
        report.update(
            {
                "source_text_sha256": snapshot["text_sha256"],
                "reference_template": case_spec["template"],
                "reference_template_sha256": template_hash,
                "renderer": "independent-audit-draft",
                "human_review_required": True,
            }
        )
        dump_json(staging / "转换核验报告.json", report)
        manifest = {
            "manifest_version": "1.0.0",
            "generator_version": GENERATOR_VERSION,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "author": AUTHOR,
            "case_type": mapping["case_type"],
            "source_text_sha256": snapshot["text_sha256"],
            "reference_template_sha256": template_hash,
            "validation_status": "machine-check-passed-human-review-required",
            "files": [
                {
                    "file": docx_path.name,
                    "sha256": sha256_bytes(docx_path.read_bytes()),
                },
                {
                    "file": "转换核验报告.json",
                    "sha256": sha256_bytes((staging / "转换核验报告.json").read_bytes()),
                },
            ],
        }
        dump_json(staging / "generation-manifest.json", manifest)
        os.replace(staging, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
