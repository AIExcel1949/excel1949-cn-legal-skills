#!/usr/bin/env python3
"""Render a first-instance attorney's brief (一审代理词) into a court-formatted DOCX.

Typography follows the civil-prosecution-brief court-filing contract
(user-authored reference contract, 2026-08):
  - Entire document in Noto Serif SC (思源宋体, SIL OFL); title 18pt REGULAR
    (not bold), centered
  - Section headings (一、二、…) bold 14pt; body 14pt regular
  - Fixed line spacing 25pt; first-line indent 28pt (2 chars)
  - Margins: left 25mm / right 20mm / top 30mm / bottom 20mm
  - Structure: title → intro labels (案由/委托人/相对方) → body sections
    (heading + paragraphs) → 此致 → court (flush left) → 2 spacer paragraphs
    → 代理人 (indent ~15 chars) → date in Chinese uppercase numerals
    (二〇二六年八月十日)
  - Compact brand header/footer (small header logo + brand name + page number)

Inputs (either one):
  --input   brief JSON: {"title", "case", "court", "attorney", "client",
            "opponent", "date" (YYYY-MM-DD), "body_sections":
            [{"heading": "一、…", "paragraphs": ["…"]}]}
  --markdown  hearing-brief Markdown draft (parse `#`/`##` headings,
            numbered-list and plain paragraphs; skips blockquotes, task
            checklists and the 待律师复核清单 work section)

Refuses to overwrite an existing output. Final print is a JSON status line.

Usage:
    python3 render_docx.py --input brief.json --output <dir>/一审代理词.docx
    python3 render_docx.py --markdown 一审代理词（草稿）.md --output <dir>/一审代理词.docx
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

CN_LEGAL_CORE = Path(__file__).resolve().parent.parent.parent / "cn-legal-core"
BODY_FONT = "Noto Serif SC"  # 思源宋体 OFL，替代系统受限字体

DATE_CN_DIGITS = {"0": "〇", "1": "一", "2": "二", "3": "三", "4": "四",
                  "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}

DEFAULT_TITLE = "一审代理词"


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


def _cn_num(n: int) -> str:
    """1->一, 10->十, 12->十二, 21->二十一, 31->三十一 (Chinese uppercase numerals)."""
    if n < 10:
        return DATE_CN_DIGITS[str(n)]
    if n == 10:
        return "十"
    tens, ones = divmod(n, 10)
    tens_part = "十" if tens == 1 else f"{DATE_CN_DIGITS[str(tens)]}十"
    return tens_part + (DATE_CN_DIGITS[str(ones)] if ones else "")


def cn_date(text: str) -> str:
    """'2026-08-10' -> '二〇二六年八月十日'; non-date strings pass through.

    Years are digit-by-digit (二〇二六), months/days follow Chinese numeral
    conventions (十、十二、二十一、三十一).
    """
    parts = text.strip().split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return text

    def to_cn_year(digits: str) -> str:
        return "".join(DATE_CN_DIGITS[d] for d in digits)

    year, month, day = parts
    return f"{to_cn_year(year)}年{_cn_num(int(month))}月{_cn_num(int(day))}日"


def normalize_title(text: str) -> str:
    """'# 一审代理词（草稿，原告代理人）' -> '一审代理词' (strip draft annotations)."""
    stripped = text.strip().lstrip("#").strip()
    return stripped.split("（", 1)[0].strip() or DEFAULT_TITLE


# --- Markdown draft parsing -------------------------------------------------

_META_PATTERNS = (
    ("case", re.compile(r"案由\s*[:：]\s*(.+)")),
    ("court", re.compile(r"受诉法院\s*[:：]\s*(.+)")),
    ("client", re.compile(r"委托人[（(].*?[）)]?\s*[:：]\s*(.+)")),
    ("opponent", re.compile(r"相对方[（(].*?[）)]?\s*[:：]\s*(.+)")),
    ("attorney", re.compile(r"代理人\s*[:：]\s*(.+)")),
)
_SKIP_SECTION_RE = re.compile(r"复核|清单|待办|工作事项")
# AI 起草状态声明（草稿元信息，不属于代理意见本体）：句子级剔除，保留同段实质内容
_DRAFT_NOTE_RE = re.compile(r"（本|AI 辅助起草|待承办律师复核后采用|待执业律师逐项复核确认")


def _strip_draft_notes(text: str) -> str:
    """Remove AI-drafting disclaimer sentences, keep the rest of the paragraph."""
    sentences = re.split(r"(?<=[。！？])", text)
    kept = [s for s in sentences if not _DRAFT_NOTE_RE.search(s)]
    return "".join(kept).strip()


def parse_markdown(path: Path) -> dict:
    """Parse a hearing-brief Markdown draft into the brief-JSON structure.

    Recognizes `#` (document title), `##`/`###` (body section headings),
    numbered-list and plain lines (body paragraphs). Skips blockquotes
    (`>` status metadata, with 案由/受诉法院/委托人/相对方 extracted),
    task checklists (`- [ ]`), and the 待律师复核清单 work section.
    """
    brief = {"title": DEFAULT_TITLE, "body_sections": []}
    current: dict | None = None
    skip_section = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("# "):
            if not brief.get("title") or brief["title"] == DEFAULT_TITLE:
                brief["title"] = normalize_title(stripped)
            continue

        if stripped.startswith("## ") or stripped.startswith("### "):
            heading = stripped.lstrip("#").strip()
            skip_section = bool(_SKIP_SECTION_RE.search(heading))
            if not skip_section:
                current = {"heading": heading, "paragraphs": []}
                brief["body_sections"].append(current)
            else:
                current = None
            continue

        if stripped.startswith(">"):
            _extract_meta(brief, stripped)
            continue

        if re.match(r"^[-*]\s*\[[ xX]\]", stripped):
            continue  # task checklist

        if skip_section or current is None:
            continue

        paragraph = _strip_draft_notes(re.sub(r"^\d+[\.、]\s*", "", stripped))
        if paragraph:
            current["paragraphs"].append(paragraph)
    return brief


def _extract_meta(brief: dict, line: str) -> None:
    body = line.lstrip(">").strip()
    for key, pattern in _META_PATTERNS:
        match = pattern.search(body)
        if match and not brief.get(key):
            brief[key] = match.group(1).strip()
            break


# --- DOCX rendering ---------------------------------------------------------

def render(brief: dict) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    # Title: 思源宋体 18pt REGULAR, centered (not bold)
    add_para(doc, brief.get("title") or DEFAULT_TITLE, size=18, bold=True, align="center")
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）

    # Intro labels (bold label inline, content regular)
    for key, label in (("case", "案由："), ("client", "委托人："),
                       ("opponent", "相对方：")):
        if brief.get(key):
            add_label_para(doc, label, str(brief[key]))

    # Body sections
    for item in brief.get("body_sections", []):
        heading = (item.get("heading") or "").strip()
        if heading:
            add_para(doc, heading, bold=True, first_indent=28)
        for paragraph in item.get("paragraphs", []):
            if str(paragraph).strip():
                add_para(doc, str(paragraph), first_indent=28)

    # Closing
    add_para(doc, "此致", first_indent=28)
    court = brief.get("court", "").strip()
    if court:
        add_para(doc, court)  # flush left, no indent
    else:
        add_para(doc, "＿＿＿＿人民法院", first_indent=0)

    # Two spacer paragraphs
    for _ in range(2):
        add_para(doc, "", first_indent=28)

    # Signature block: 代理人 indented ~15 chars, date with Chinese numerals
    attorney = (brief.get("attorney") or "").strip() or "＿＿＿＿＿"
    add_para(doc, f"代理人：{attorney}", first_indent=210)
    date_text = (brief.get("date") or "").strip()
    if date_text:
        add_para(doc, cn_date(date_text), first_indent=140)
    else:
        add_para(doc, "＿＿＿＿年＿＿月＿＿日", first_indent=140)

    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染一审代理词 DOCX（法院参考排版）")
    parser.add_argument("--input", type=Path, help="代理词正文 JSON 路径")
    parser.add_argument("--markdown", type=Path, help="代理词草稿 Markdown 路径")
    parser.add_argument("--output", type=Path, default=Path("一审代理词.docx"),
                        help="输出 docx 路径（默认：一审代理词.docx，不得已存在）")
    args = parser.parse_args()

    if args.input is None and args.markdown is None:
        print("[ERROR] 必须提供 --input（JSON）或 --markdown（草稿）之一", file=sys.stderr)
        return 1
    if args.input is not None and args.markdown is not None:
        print("[WARN] 同时提供了 --input 与 --markdown，优先使用 --input", file=sys.stderr)

    if args.input is not None:
        brief = json.loads(args.input.read_text(encoding="utf-8"))
        brief.setdefault("title", DEFAULT_TITLE)
        brief.setdefault("body_sections", [])
        source = str(args.input)
    else:
        brief = parse_markdown(args.markdown)
        source = str(args.markdown)

    doc = render(brief)
    if args.output.exists():
        raise FileExistsError(f"拒绝覆盖：{args.output}")

    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py", "cn_legal_core_brand")
    with tempfile.TemporaryDirectory(prefix=".cn-hearing-docx-") as temporary:
        raw_path = Path(temporary) / "raw.docx"
        doc.save(raw_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            docx_brand.brand_docx(
                raw_path, args.output,
                title=DEFAULT_TITLE, subject="AI辅助生成，须由执业律师逐项核验",
                compact=True,
            )
        except Exception:
            if args.output.exists():
                args.output.unlink()
            raise
    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "source": source,
        "title": brief.get("title") or DEFAULT_TITLE,
        "author": "AIOffice职场通关-excel1949",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FileExistsError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
