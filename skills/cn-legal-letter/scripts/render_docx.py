#!/usr/bin/env python3
"""将律师函 JSON 渲染为正式《律师函》DOCX。

输入兼容两种形态（自动识别）：
  1. build_letter.py 产出的 legal-letter.json（含 "draft" 包装，sender/recipient/
     facts/demands/delivery_channels）；
  2. schemas/letter-input.schema.json 的原始输入（sender/recipient/facts/
     authorities/calculations/demands/delivery_channels 平铺在顶层）。
  可选扩展字段（lawyer 律师姓名、law_firm 律师事务所、deadline 履行期限、
  date 发函日期）存在时优先采用，缺失时以占位符留待执业律师复核。

排版约定（2026-08 函件排版契约，与 cn-complaint 渲染器一致）：
  - 全文思源宋体 Noto Serif SC（OFL 免费可商用）；标题"律师函"18pt 常规字重、
    居中（非粗体）；正文 14pt 常规
  - 固定行距 25pt；首行缩进 28pt（两字符）
  - 页边距：左 25mm / 右 20mm / 上 30mm / 下 20mm
  - 结构：标题 → 致：收件人 → 事实陈述（连续叙事）→ 法律依据 → 要求事项
    （中文序号 一、二、）→ 履行期限 → 此致 + 收件人 → 落款
    （律师事务所 + 律师 + 中文大写日期，如 二〇二六年八月十日）
  - compact 品牌页眉（小 Logo），页脚清空

用法：
    python3 render_docx.py --input <letter.json> --output <dir>/律师函.docx
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
BODY_FONT = "Noto Serif SC"  # 思源宋体 OFL，免费可商用

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
    """标签加粗内联、内容常规，同一段（首行缩进两字符）。"""
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
    """1 -> 一, 12 -> 十二, 21 -> 二十一（要求事项序号）。"""
    if n <= 10:
        return CN_DIGITS[n - 1]
    tens, ones = divmod(n, 10)
    tens_char = CN_DIGITS[tens - 1] if tens > 1 else ""
    return f"{tens_char}十" + (CN_DIGITS[ones - 1] if ones else "")


def _cn_num_1_99(n: int) -> str:
    """1->一, 10->十, 12->十二, 21->二十一, 30->三十（中文大写日期用）。"""
    if 1 <= n <= 9:
        return CN_DIGITS[n - 1]
    if n == 10:
        return "十"
    tens, ones = divmod(n, 10)
    tens_char = CN_DIGITS[tens - 1] if tens > 1 else ""
    return f"{tens_char}十" + (CN_DIGITS[ones - 1] if ones else "")


def cn_date(text: str) -> str:
    """'2026-08-10' -> '二〇二六年八月十日'；非日期字符串原样返回。"""
    parts = text.strip().split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return text

    def to_cn_year(digits: str) -> str:
        return "".join(DATE_CN_DIGITS[d] for d in digits)

    year, month, day = parts
    month_cn = _cn_num_1_99(int(month))
    day_cn = _cn_num_1_99(int(day))
    return f"{to_cn_year(year)}年{month_cn}月{day_cn}日"


def as_text(value) -> str:
    """字典取 text 字段，字符串原样，其余转 str。"""
    if isinstance(value, dict):
        return str(value.get("text", "") or "")
    if isinstance(value, str):
        return value
    return str(value) if value is not None else ""


def normalize(payload: dict) -> dict:
    """兼容原始输入与 build_letter.py 输出（draft 包装），并合并顶层可选扩展字段。"""
    draft = payload.get("draft")
    if isinstance(draft, dict):
        merged = dict(draft)
        for key in ("authorities", "calculations", "law_firm", "lawyer",
                    "deadline", "date", "期限"):
            if merged.get(key) is None and payload.get(key) is not None:
                merged[key] = payload[key]
        return merged
    return payload


def render(letter: dict) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    recipient = as_text(letter.get("recipient", ""))
    sender = as_text(letter.get("sender", ""))
    facts = letter.get("facts", []) or []
    authorities = letter.get("authorities", []) or []
    demands = letter.get("demands", []) or []
    law_firm = str(letter.get("law_firm") or "").strip()
    lawyer = str(letter.get("lawyer") or "").strip()
    deadline = str(letter.get("deadline") or letter.get("期限") or "").strip()
    date = str(letter.get("date") or "").strip()

    # 标题：18pt 常规字重、居中（非粗体）
    add_para(doc, "律师函", size=18, bold=True, align="center")
    # 标题后大间距
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）

    # 致送对象
    if recipient:
        add_label_para(doc, "致：", recipient)

    # 事实陈述（连续叙事，不加小节标题）
    for fact in facts:
        text = as_text(fact)
        if text:
            add_para(doc, text, first_indent=28)

    # 法律依据
    add_label_para(doc, "法律依据：", "")
    if authorities:
        for authority in authorities:
            title = authority.get("title") if isinstance(authority, dict) else authority
            title = as_text(title)
            if title:
                add_para(doc, title, first_indent=28)
    else:
        add_para(doc, "＿＿＿＿（由执业律师复核后补列）", first_indent=28)

    # 要求事项（中文序号 一、二、……）
    add_label_para(doc, "要求事项：", "")
    for index, demand in enumerate(demands, 1):
        text = as_text(demand)
        if text:
            add_para(doc, f"{cn_number(index)}、{text}", first_indent=28)

    # 履行期限
    if deadline:
        add_label_para(doc, "履行期限：", deadline)
    else:
        add_para(doc, "履行期限：＿＿＿＿（由执业律师复核后确定）", first_indent=28)

    # 此致 + 收件人
    add_para(doc, "此致", first_indent=28)
    if recipient:
        add_para(doc, recipient)

    # 两个空行
    for _ in range(2):
        add_para(doc, "", first_indent=28)

    # 落款：律师事务所 + 律师 + 中文大写日期
    if not law_firm and not lawyer and sender:
        add_para(doc, sender, first_indent=210)
    else:
        add_para(doc, f"律师事务所：{law_firm or '＿＿＿＿'}", first_indent=210)
        add_para(doc, f"律师：{lawyer or '＿＿＿＿'}", first_indent=210)
    if date:
        add_para(doc, cn_date(date), first_indent=140)
    else:
        add_para(doc, "＿＿＿＿年＿＿月＿＿日", first_indent=140)

    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染律师函 DOCX（思源宋体正式函件排版）")
    parser.add_argument("--input", type=Path, required=True,
                        help="律师函 JSON 路径（build_letter.py 输出或 letter-input 原始输入）")
    parser.add_argument("--output", type=Path, required=True,
                        help="输出 docx 路径（不得已存在）")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    letter = normalize(payload)

    doc = render(letter)
    if args.output.exists():
        raise FileExistsError(f"拒绝覆盖：{args.output}")

    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py",
                             "cn_legal_core_brand")
    with tempfile.TemporaryDirectory(prefix=".cn-legal-letter-docx-") as temporary:
        raw_path = Path(temporary) / "raw.docx"
        doc.save(raw_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            docx_brand.brand_docx(
                raw_path, args.output,
                title="律师函", subject="AI辅助生成，须由执业律师逐项核验",
                compact=True,
            )
        except Exception:
            if args.output.exists():
                args.output.unlink()
            raise
    print(json.dumps({"ok": True, "output": str(args.output),
                      "author": "AIOffice职场通关-excel1949"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
