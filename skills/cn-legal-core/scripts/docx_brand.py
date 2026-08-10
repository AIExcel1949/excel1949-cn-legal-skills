#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


AUTHOR = "AIOffice职场通关-excel1949"
BRAND = "AIOffice职场通关"
CATEGORY = "AIOffice职场通关法律Skill"
COMMENT = "AI辅助生成，须由执业律师逐项核验"
NS = {
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
}


try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
except ImportError as exc:
    raise RuntimeError("缺少 python-docx，请先安装项目依赖") from exc


def require_docx() -> tuple[object, object, object, object, object]:
    return Document, WD_ALIGN_PARAGRAPH, OxmlElement, qn, Cm


def clear_container(container: object) -> None:
    element = container._element
    for child in list(element):
        element.remove(child)


def add_page_field(run: object, OxmlElement: object, qn: object) -> None:
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend((begin, instruction, end))


def set_header(header: object, logo: Path, width: object, alignment: object,
              qr_path: Path | None = None, qr_width: object | None = None,
              usable_width: object | None = None) -> None:
    """页眉统一标准（2026-08-10 用户确认）：Logo 左上角，二维码右上角（同一行）。"""
    clear_container(header)
    paragraph = header.add_paragraph()
    paragraph.alignment = alignment.LEFT
    shape = paragraph.add_run().add_picture(str(logo), width=width)
    max_height_pt = shape.height.pt
    if qr_path is not None and qr_path.is_file():
        if usable_width is not None:
            paragraph.paragraph_format.tab_stops.add_tab_stop(
                usable_width, alignment.RIGHT
            )
        paragraph.add_run("\t")
        qr_shape = paragraph.add_run().add_picture(str(qr_path), width=qr_width or Cm(1.2))
        max_height_pt = max(max_height_pt, qr_shape.height.pt)
    # 段落行高 AT_LEAST 匹配最高图片，防止 Logo/二维码被裁切
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
    paragraph.paragraph_format.line_spacing = Pt(max_height_pt + 4)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)


def set_footer(
    footer: object,
    logo: Path | None,
    width: object | None,
    alignment: object,
    OxmlElement: object,
    qn: object,
) -> None:
    """页脚统一标准（2026-08-10 用户确认）：仅居中页码，不要其他内容。"""
    clear_container(footer)
    paragraph = footer.add_paragraph()
    paragraph.alignment = alignment.CENTER
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.add_run("第 ")
    page_run = paragraph.add_run()
    add_page_field(page_run, OxmlElement, qn)
    paragraph.add_run(" 页")


def set_company(docx_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="docx-props-", dir=docx_path.parent) as temp_name:
        temp = Path(temp_name)
        with zipfile.ZipFile(docx_path, "r") as archive:
            total_size = 0
            for member in archive.infolist():
                pure = PurePosixPath(member.filename)
                if pure.is_absolute() or ".." in pure.parts:
                    raise ValueError(f"OOXML 路径异常：{member.filename}")
                total_size += member.file_size
                if member.file_size > 100 * 1024 * 1024:
                    raise ValueError(f"OOXML 成员过大：{member.filename}")
            if total_size > 500 * 1024 * 1024:
                raise ValueError("OOXML 解压后总体积过大")
            archive.extractall(temp)
        app_path = temp / "docProps" / "app.xml"
        tree = ET.parse(app_path)
        root = tree.getroot()
        company = root.find("ep:Company", NS)
        if company is None:
            company = ET.SubElement(root, f"{{{NS['ep']}}}Company")
        company.text = BRAND
        tree.write(app_path, encoding="UTF-8", xml_declaration=True)
        rebuilt = temp / "rebuilt.docx"
        with zipfile.ZipFile(rebuilt, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(temp.rglob("*")):
                if item.is_file() and item != rebuilt:
                    archive.write(item, item.relative_to(temp).as_posix())
        shutil.move(rebuilt, docx_path)


def load_brand_config() -> dict:
    """读取 brand.json 品牌配置（不存在返回空 dict）。"""
    config_path = Path(__file__).resolve().parent.parent / "assets" / "brand" / "brand.json"
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def brand_docx(input_path: Path, output_path: Path, title: str, subject: str, compact: bool = False, qr_code: Path | None = None) -> None:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("输入与输出路径必须不同，不得覆盖原件")
    if not input_path.is_file() or input_path.suffix.lower() != ".docx":
        raise ValueError("输入必须是存在的 DOCX 文件")
    if output_path.exists():
        raise FileExistsError(f"输出文件已存在：{output_path}")

    skill_root = Path(__file__).resolve().parent.parent
    brand_dir = skill_root / "assets" / "brand"
    header_logo = brand_dir / "header-logo.png"
    footer_logo = brand_dir / "footer-logo.png"
    if not header_logo.is_file() or not footer_logo.is_file():
        raise FileNotFoundError("缺少页眉或页脚 Logo 发布副本")

    Document, alignment, OxmlElement, qn, Cm = require_docx()
    document = Document(str(input_path))
    props = document.core_properties
    props.author = AUTHOR
    props.last_modified_by = AUTHOR
    props.title = title
    props.subject = subject
    props.category = CATEGORY
    props.comments = COMMENT

    # 孤行控制（2026-08-10 用户要求）：所有 DOCX 段落开启 widow control，
    # 避免出现"一页只有一行"的孤行；由 Word 渲染时自动调整
    for paragraph in document.paragraphs:
        paragraph.paragraph_format.widow_control = True
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.widow_control = True

    settings = document.settings.element
    even = settings.find(qn("w:evenAndOddHeaders"))
    if even is None:
        settings.append(OxmlElement("w:evenAndOddHeaders"))

    # 页眉页脚统一标准（2026-08-10 用户确认）：所有 DOCX 一致——
    # 页眉 = Logo 左上 + 二维码右上（同一行）；页脚 = 仅居中页码。
    header_width = Cm(1.5) if compact else Cm(1.8)
    brand_config = load_brand_config()
    qr_name = brand_config.get("qr_code", "qr-code.png")
    qr_path = Path(__file__).resolve().parent.parent / "assets" / "brand" / qr_name
    resolved_qr = qr_code if qr_code is not None else (qr_path if qr_path.is_file() else None)
    for section in document.sections:
        usable = section.page_width - section.left_margin - section.right_margin
        section.header.is_linked_to_previous = False
        set_header(section.header, header_logo, header_width, alignment,
                   qr_path=resolved_qr, qr_width=Cm(1.2), usable_width=usable)
        set_footer(section.footer, None, None, alignment, OxmlElement, qn)
        if section.different_first_page_header_footer:
            section.first_page_header.is_linked_to_previous = False
            set_header(section.first_page_header, header_logo, header_width, alignment,
                       qr_path=resolved_qr, qr_width=Cm(1.2), usable_width=usable)
            set_footer(section.first_page_footer, None, None, alignment, OxmlElement, qn)
        section.even_page_header.is_linked_to_previous = False
        section.even_page_footer.is_linked_to_previous = False
        set_header(section.even_page_header, header_logo, header_width, alignment,
                   qr_path=resolved_qr, qr_width=Cm(1.2), usable_width=usable)
        set_footer(section.even_page_footer, None, None, alignment, OxmlElement, qn)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    set_company(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="为 DOCX 工作副本写入 AIOffice 品牌和统一属性")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--subject", required=True)
    args = parser.parse_args()
    try:
        brand_docx(args.input, args.output, args.title, args.subject)
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    result = {"output": str(args.output), "author": AUTHOR, "brand": BRAND}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
