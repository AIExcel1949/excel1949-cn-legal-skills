#!/usr/bin/env python3
"""Render defense.json into a court-formatted Civil Defense Statement (民事答辩状) DOCX.

Typography follows the same court-filing contract as cn-complaint
(user-authored reference contract, 2026-08):
  - Noto Serif SC (思源宋体 OFL，替代系统仿宋防侵权); title 18pt REGULAR
    (not bold), centered
  - Body 14pt; fixed line spacing 25pt; first-line indent 28pt (2 chars)
  - Margins: left 25mm / right 20mm / top 30mm / bottom 20mm
  - Structure: title → 答辩人 → 被答辩人 → 案由 → 答辩意见 (response_matrix
    itemized: original claim verbatim + per-claim response stance and text)
    → 事实与理由 (independent_defenses + defensive_facts) → 此致 → court →
    signature 答辩人 + date in Chinese uppercase numerals
  - Compact brand header/footer via cn-legal-core docx_brand; existing output
    is never overwritten

Contract notes (defense-output.schema.json v1.0): the schema carries no
plaintiff / cause of action / court / date fields, so those sections are
rendered as underscore placeholders when absent and reported in the JSON
notes; the renderer never fabricates party names or defense text.

Usage:
    python3 render_docx.py --input defense.json --output <dir>/民事答辩状.docx
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

STANCE_LABELS = {
    "admit": "承认",
    "deny": "否认",
    "lack_knowledge": "不知悉",
    "procedural_objection": "程序异议",
    "unanswered": "未回应",
}
UNANSWERED_TEXT = "该项诉请未获得明示答辩，依契约不得视为承认，须由执业律师补充答辩意见。"


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
    """1 -> 一, 12 -> 十二, 21 -> 二十一 (Chinese numeral for item lists)."""
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


def party_line(value, label: str, known_prefixes: tuple[str, ...]) -> tuple[str, str]:
    """Normalize a party value (str or {'text': ...}) into (label, content).

    When the text already carries a party prefix such as "答辩人（被告）：",
    the embedded label is reused verbatim instead of being duplicated.
    """
    text = value.get("text", "") if isinstance(value, dict) else str(value or "")
    text = text.strip()
    if not text:
        return f"{label}：", ""
    if text.startswith(known_prefixes):
        idx = text.find("：")
        if idx == -1:
            return f"{label}：", text
        return text[: idx + 1], text[idx + 1:]
    return f"{label}：", text


def render(defense: dict) -> tuple[Document, list[str]]:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    respondent = defense.get("respondent", {})
    plaintiff = defense.get("plaintiff") or defense.get("complainant") or defense.get("claimant")
    case_type = defense.get("case_type", {})
    matrix = defense.get("response_matrix", [])
    defenses = defense.get("independent_defenses", [])
    facts = defense.get("defensive_facts", [])
    court = defense.get("court", {})
    as_of = defense.get("as_of_date", "")

    placeholders: list[str] = []

    # Title: 思源宋体 18pt REGULAR, centered (not bold)
    add_para(doc, "民事答辩状", size=18, bold=True, align="center")
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）

    # 答辩人
    resp_label, resp_content = party_line(respondent, "答辩人", ("答辩人",))
    add_label_para(doc, resp_label, resp_content)
    # 被答辩人
    if plaintiff:
        plain_label, plain_content = party_line(plaintiff, "被答辩人", ("被答辩人", "原告"))
        add_label_para(doc, plain_label, plain_content)
    else:
        placeholders.append("被答辩人信息")
        add_label_para(doc, "被答辩人：", "＿＿＿＿＿＿＿＿＿＿＿＿")

    # 案由
    case_text = case_type.get("text", "") if isinstance(case_type, dict) else str(case_type or "")
    if case_text.strip():
        add_label_para(doc, "案由：", case_text.strip())
    else:
        placeholders.append("案由")
        add_label_para(doc, "案由：", "＿＿＿＿＿＿＿＿＿＿＿＿")

    # 答辩意见：response_matrix 逐项回应（原告诉请原文 + 回应结论）
    add_label_para(doc, "答辩意见：", "")
    for index, row in enumerate(matrix, 1):
        claim = row.get("claim_text_verbatim", "").strip()
        add_para(doc, f"{cn_number(index)}、原告诉请：{claim}", first_indent=28)
        stance = STANCE_LABELS.get(row.get("stance", ""), row.get("stance", ""))
        response = (row.get("response_text") or "").strip()
        if response:
            add_para(doc, f"答辩人对此项诉请持{stance}立场：{response}", first_indent=28)
        else:
            add_para(doc, f"答辩人对此项诉请持{stance}立场：{UNANSWERED_TEXT}", first_indent=28)

    # 事实与理由：独立抗辩（编号）+ 答辩事实（叙述段落）
    add_label_para(doc, "事实与理由：", "")
    for index, item in enumerate(defenses, 1):
        add_para(doc, f"{cn_number(index)}、{item.get('text', '').strip()}", first_indent=28)
    for fact in facts:
        add_para(doc, fact.get("text", "").strip(), first_indent=28)

    # 此致 + 法院
    add_para(doc, "此致", first_indent=28)
    court_text = court.get("text", "") if isinstance(court, dict) else str(court or "")
    if court_text.strip():
        add_para(doc, court_text.strip())  # flush left, no indent
    else:
        placeholders.append("受诉法院")
        add_para(doc, "＿＿＿＿＿＿＿＿人民法院")

    # Two spacer paragraphs (with first-line indent)
    for _ in range(2):
        add_para(doc, "", first_indent=28)

    # Signature block: 答辩人 indented ~15 chars, date with Chinese numerals
    add_para(doc, "答辩人：", first_indent=210)
    if as_of:
        add_para(doc, cn_date(as_of), first_indent=140)
    else:
        placeholders.append("答辩日期")
        add_para(doc, "＿＿＿＿年＿＿月＿＿日", first_indent=140)

    return doc, placeholders


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染民事答辩状 DOCX（法院参考排版）")
    parser.add_argument("--input", type=Path, required=True, help="defense.json 路径")
    parser.add_argument("--output", type=Path, required=True, help="输出 docx 路径（不得已存在）")
    args = parser.parse_args()

    defense = json.loads(args.input.read_text(encoding="utf-8"))

    doc, placeholders = render(defense)
    if args.output.exists():
        raise FileExistsError(f"拒绝覆盖：{args.output}")

    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py", "cn_legal_core_brand")
    with tempfile.TemporaryDirectory(prefix=".cn-defense-docx-") as temporary:
        raw_path = Path(temporary) / "raw.docx"
        doc.save(raw_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            docx_brand.brand_docx(
                raw_path, args.output,
                title="民事答辩状", subject="AI辅助生成，须由执业律师逐项核验",
                compact=True,
            )
        except Exception:
            if args.output.exists():
                args.output.unlink()
            raise
    result = {"ok": True, "output": str(args.output), "author": "AIOffice职场通关-excel1949"}
    if placeholders:
        result["notes"] = f"以下信息在 defense.json 中缺失，已用占位符代替，须由律师补充：{'、'.join(dict.fromkeys(placeholders))}"
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
