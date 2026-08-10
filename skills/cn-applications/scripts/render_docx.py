#!/usr/bin/env python3
"""将程序申请工作底稿 JSON 渲染为《证据保全申请书》DOCX。

排版遵循法院申请书参考规范（法〔2025〕82号 示范文本要素）：
  - 全文思源宋体 Noto Serif SC（SIL OFL 免费商用，替代系统仿宋防侵权）
  - 标题「证据保全申请书」18pt 居中非粗体；正文 14pt
  - 行距固定 25pt；首行缩进 28pt（2 字符）
  - 页边距：上 30mm / 下 20mm / 左 25mm / 右 20mm
  - 结构：标题 → 申请人 → 被申请人 → 案由 → 申请事项（中文数字编号）
    → 事实与理由（连续叙述，含紧急性理由）→ 此致 → 受理法院 →
    申请人署名 → 中文大写日期
  - 紧凑品牌页眉页脚（brand_docx compact=True）

输入契约：cn-applications 程序申请工作底稿 JSON（schema_version 1.0）。
接受两种形态：
  1. application-input.schema.json 的原始输入；
  2. application-workpaper.json（含 source_record 包装，取 source_record）。
申请人、被申请人、案由为渲染扩展字段（applicant / respondent /
cause_of_action，兼容 client_name / opponent_name / case_cause），
缺失时以下划线占位供律师手填，不阻断渲染。

用法：
    python3 render_docx.py --input application.example.json --output <目录>/证据保全申请书.docx
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
BODY_FONT = "Noto Serif SC"  # 思源宋体 OFL，免费商用

CN_DIGITS = "一二三四五六七八九十"
DATE_CN_DIGITS = {"0": "〇", "1": "一", "2": "二", "3": "三", "4": "四",
                  "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
PLACEHOLDER = "＿＿＿＿＿＿＿＿＿＿"  # 全角下划线占位，供律师手填


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
    """标签加粗行内、内容常规，同段（2 字符首行缩进）。"""
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
    """1 -> 一, 12 -> 十二, 21 -> 二十一（申请事项中文数字编号）。"""
    if n <= 10:
        return CN_DIGITS[n - 1]
    tens, ones = divmod(n, 10)
    tens_char = CN_DIGITS[tens - 1] if tens > 1 else ""
    return f"{tens_char}十" + (CN_DIGITS[ones - 1] if ones else "")


def cn_int(value: int) -> str:
    """1-31 转中文数字：1->一, 10->十, 18->十八, 21->二十一, 30->三十。"""
    tens, ones = divmod(value, 10)
    if tens == 0:
        return CN_DIGITS[ones - 1]
    if tens == 1:
        return "十" + (CN_DIGITS[ones - 1] if ones else "")
    return CN_DIGITS[tens - 1] + "十" + (CN_DIGITS[ones - 1] if ones else "")


def cn_date(text: str) -> str:
    """'2022-03-21' -> '二〇二二年三月二十一日'；非日期字符串原样通过。"""
    parts = text.strip().split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return text
    year, month, day = parts
    year_cn = "".join(DATE_CN_DIGITS[d] for d in year)
    return f"{year_cn}年{cn_int(int(month))}月{cn_int(int(day))}日"


def get_first(data: dict, *keys: str) -> str:
    """按序取第一个非空字符串字段。"""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def render(application: dict) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    applicant = get_first(application, "applicant", "applicant_name", "client_name") or PLACEHOLDER
    respondent = get_first(application, "respondent", "respondent_name", "opponent_name") or PLACEHOLDER
    cause = get_first(application, "cause_of_action", "case_cause") or PLACEHOLDER
    reliefs = application.get("requested_relief", [])
    facts = application.get("supporting_facts", [])
    urgency = application.get("urgency", {}) or {}
    reasons = urgency.get("reasons", [])
    tribunal = application.get("tribunal") or ""
    as_of = application.get("as_of_date", "")

    # 标题：18pt 居中非粗体
    add_para(doc, "证据保全申请书", size=18, bold=True, align="center")
    # 标题后留白（固定行距 58pt 的空段落）
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）

    # 当事人与案由
    add_label_para(doc, "申请人：", applicant)
    add_label_para(doc, "被申请人：", respondent)
    add_label_para(doc, "案由：", cause)

    # 申请事项（中文数字编号）
    add_label_para(doc, "申请事项：", "")
    for index, relief in enumerate(reliefs, 1):
        add_para(doc, f"{cn_number(index)}、{relief.get('text', '')}", first_indent=28)

    # 事实与理由：连续叙述，含紧急性理由
    add_label_para(doc, "事实与理由：", "")
    for fact in facts:
        add_para(doc, fact.get("text", ""), first_indent=28)
    for reason in reasons:
        add_para(doc, reason.get("text", ""), first_indent=28)

    # 结尾：此致 → 受理法院 → 署名 → 中文大写日期
    add_para(doc, "此致", first_indent=28)
    add_para(doc, tribunal)  # 顶格，法院缺失时留空行

    for _ in range(2):
        add_para(doc, "", first_indent=28)

    add_para(doc, "申请人：", first_indent=210)
    if as_of:
        add_para(doc, cn_date(as_of), first_indent=140)
    else:
        add_para(doc, "＿＿＿＿年＿＿月＿＿日", first_indent=140)

    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染《证据保全申请书》DOCX（法院参考排版）")
    parser.add_argument("--input", type=Path, required=True, help="程序申请工作底稿 JSON 路径")
    parser.add_argument("--output", type=Path, required=True, help="输出 docx 路径（不得已存在）")
    args = parser.parse_args()

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        application = data.get("source_record") if "source_record" in data else data

        doc = render(application)
        if args.output.exists():
            raise FileExistsError(f"拒绝覆盖：{args.output}")

        docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py", "cn_legal_core_brand")
        with tempfile.TemporaryDirectory(prefix=".cn-applications-docx-") as temporary:
            raw_path = Path(temporary) / "raw.docx"
            doc.save(raw_path)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            try:
                docx_brand.brand_docx(
                    raw_path, args.output,
                    title="证据保全申请书", subject="AI辅助生成，须由执业律师逐项核验",
                    compact=True,
                )
            except Exception:
                if args.output.exists():
                    args.output.unlink()
                raise
    except (OSError, ValueError, json.JSONDecodeError, FileExistsError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "output": str(args.output), "author": "AIOffice职场通关-excel1949"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
