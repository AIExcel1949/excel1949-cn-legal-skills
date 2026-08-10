#!/usr/bin/env python3
"""Render cn-contract-review JSON output into a formal 合同审查报告 DOCX.

Typography follows the skill's report contract (2026-08):
  - Body font: Noto Serif SC (思源宋体, SIL OFL, free for commercial use)
  - Title "合同审查报告" 18pt REGULAR (not bold), centered
  - Body 14pt; fixed line spacing 25pt; first-line indent 28pt (2 chars)
  - Margins: left 25mm / right 20mm / top 30mm / bottom 20mm
  - Structure per the skill output contract:
      一、审查概况 (matter / source / status / blockers / coverage & term &
         cross-reference audit / authority registry)
      二、逐条审查发现 (条款号 / 原文逐字保留 / 风险等级 / 修改建议)
      三、风险汇总 (risk-level statistics + per-finding summary)
  - Compact brand header (small header logo only, no footer content)

Usage:
    python3 render_docx.py --input review.json --output <dir>/合同审查报告.docx
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from jsonschema import Draft202012Validator

CN_LEGAL_CORE = Path(__file__).resolve().parent.parent.parent / "cn-legal-core"
BODY_FONT = "Noto Serif SC"  # 思源宋体 OFL，免费可商用，替代系统受限字体

RISK_CN = {"high": "高", "medium": "中", "low": "低"}
EXPRESSION_CN = {"potential": "可能存在", "needs_verification": "待核验"}
BASIS_CN = {"legal": "法律", "commercial": "商业", "drafting": "起草"}
OPERATION_CN = {
    "comment": "批注",
    "replace": "替换",
    "insert_before": "前置插入",
    "insert_after": "后置插入",
    "delete": "删除",
}
EFFECT_CN = {
    "effective": "现行有效",
    "amended": "已修改",
    "repealed": "已废止",
    "not_yet_effective": "尚未生效",
    "unknown": "状态未知",
}
VERIFICATION_CN = {"verified": "已核验", "pending": "待核验", "failed": "核验失败"}
APPLICABILITY_CN = {
    "confirmed": "适用性已确认",
    "unconfirmed": "适用性未确认",
    "not_applicable": "不适用",
}
GAP_CN = {
    "missing": "缺失",
    "applicability_pending": "适用性待定",
    "not_applicable": "不适用",
}
IMPORTANCE_CN = {"blocker": "阻断", "high": "高", "medium": "中", "low": "低"}
TERM_ISSUE_CN = {"used_but_not_defined": "使用但未定义", "defined_but_not_used": "定义但未使用"}
XREF_ISSUE_CN = {"unresolved_target": "目标未解析", "declared_conflict": "声明冲突"}


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
    """Bold label inline, regular content, same paragraph (2-char first-line indent)."""
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(28)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(25)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    label_run = paragraph.add_run(label)
    set_run_font(label_run, 14, bold=True)
    if content:
        content_run = paragraph.add_run(content)
        set_run_font(content_run, 14, bold=False)
    return paragraph


def add_section_heading(doc: Document, text: str) -> None:
    """Section heading: bold 14pt, flush left, no indent (title stays the only 18pt)."""
    return add_para(doc, text, size=14, bold=True)


def add_original_text(doc: Document, text: str) -> None:
    """Render the verbatim original clause text, one paragraph per line."""
    for line in text.splitlines():
        add_para(doc, line, first_indent=28)


def load_input(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "schemas" / "review-output.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(data)
    return data


def render_overview(doc: Document, data: dict[str, Any]) -> None:
    add_section_heading(doc, "一、审查概况")
    add_label_para(doc, "案件标识：", str(data.get("matter_id", "")))
    source = data.get("source_contract", {})
    add_label_para(
        doc, "审查对象：",
        f"{source.get('file_name', '')}（源文件 SHA-256：{source.get('sha256', '')}）",
    )
    add_label_para(doc, "审查状态：", "需律师审查，红线指令均未应用。")
    if data.get("blocked"):
        add_label_para(doc, "阻断状态：", "存在阻断项，相关内容须由执业律师核验后方可使用。")
        for blocker in data.get("blockers", []):
            add_para(
                doc,
                f"{blocker.get('code', '')}：{blocker.get('message', '')}（{blocker.get('path', '')}）",
                first_indent=28,
            )
    else:
        add_label_para(doc, "阻断状态：", "未触发阻断项。")

    review_items = data.get("review_items", [])
    findings = [item for clause in review_items for item in clause.get("findings", [])]
    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        level = finding.get("risk", {}).get("level", "low")
        counts[level] = counts.get(level, 0) + 1
    add_label_para(
        doc, "审查统计：",
        f"共审查 {len(review_items)} 条条款，记录 {len(findings)} 项审查发现；"
        f"其中高风险 {counts['high']} 项、中风险 {counts['medium']} 项、低风险 {counts['low']} 项。",
    )

    gaps = data.get("coverage_gaps", [])
    if gaps:
        add_label_para(doc, "条款覆盖缺口：", "")
        for gap in gaps:
            add_para(
                doc,
                f"〔{GAP_CN.get(gap.get('gap_status', ''), gap.get('gap_status', ''))}"
                f"/{IMPORTANCE_CN.get(gap.get('importance', ''), gap.get('importance', ''))}〕"
                f"{gap.get('label', '')}：{gap.get('reason', '')}；建议：{gap.get('recommendation', '')}（未应用）",
                first_indent=28,
            )

    term_issues = data.get("defined_term_issues", [])
    if term_issues:
        add_label_para(doc, "定义词问题：", "")
        for term in term_issues:
            add_para(
                doc,
                f"〔{TERM_ISSUE_CN.get(term.get('issue_type', ''), term.get('issue_type', ''))}〕"
                f"{term.get('term', '')}",
                first_indent=28,
            )

    xrefs = data.get("cross_reference_issues", [])
    if xrefs:
        add_label_para(doc, "交叉引用问题：", "")
        for reference in xrefs:
            add_para(
                doc,
                f"〔{XREF_ISSUE_CN.get(reference.get('issue_type', ''), reference.get('issue_type', ''))}〕"
                f"{reference.get('source_clause_id', '')} → {reference.get('target_label', '')}",
                first_indent=28,
            )

    authorities = data.get("authority_records", [])
    if authorities:
        add_label_para(doc, "法源登记：", "")
        for authority in authorities:
            add_para(
                doc,
                f"{authority.get('title', '')}（{authority.get('record_id', '')}；"
                f"{EFFECT_CN.get(authority.get('effect_status', ''), authority.get('effect_status', ''))} · "
                f"{VERIFICATION_CN.get(authority.get('verification_status', ''), authority.get('verification_status', ''))} · "
                f"{APPLICABILITY_CN.get(authority.get('applicability_status', ''), authority.get('applicability_status', ''))}）",
                first_indent=28,
            )


def render_finding(doc: Document, finding: dict[str, Any], authorities: dict[str, Any]) -> None:
    add_label_para(doc, f"意见 {finding.get('finding_id', '')}", "")
    add_label_para(doc, "问题：", finding.get("issue", ""))
    risk = finding.get("risk", {})
    level = risk.get("level", "low")
    expression = risk.get("expression", "")
    add_label_para(
        doc, "风险等级：",
        f"{RISK_CN.get(level, level)}（{EXPRESSION_CN.get(expression, expression)}）",
    )
    add_label_para(
        doc, "意见类型：",
        BASIS_CN.get(finding.get("basis_type", ""), finding.get("basis_type", "")),
    )
    add_label_para(doc, "修改建议：", finding.get("suggestion", ""))
    delta = finding.get("delta", {})
    operation = delta.get("operation", "")
    add_label_para(
        doc, "变更指令：",
        f"{OPERATION_CN.get(operation, operation)}（未应用）",
    )
    if delta.get("target_text"):
        add_label_para(doc, "指令目标：", delta["target_text"])
    if delta.get("proposed_text"):
        add_label_para(doc, "指令建议：", delta["proposed_text"])
    authority_ids = finding.get("authority_ids", [])
    if authority_ids:
        names = "、".join(
            f"{authorities.get(aid, {}).get('title', aid)}（{aid}）" for aid in authority_ids
        )
        add_label_para(doc, "法源：", names)
    else:
        add_label_para(doc, "法源：", "无（非法律类意见）")


def render_items(doc: Document, data: dict[str, Any]) -> None:
    add_section_heading(doc, "二、逐条审查发现")
    review_items = data.get("review_items", [])
    if not review_items:
        add_para(doc, "本次未登记待审查条款。", first_indent=28)
        return
    authorities = {item.get("record_id", ""): item for item in data.get("authority_records", [])}
    for item in review_items:
        clause_id = item.get("clause_id", "")
        heading = item.get("heading", "")
        add_section_heading(doc, f"{heading}（{clause_id}）" if heading else clause_id)
        add_label_para(doc, "原文（逐字保留）：", "")
        add_original_text(doc, item.get("original_text", ""))
        add_label_para(doc, "原文 SHA-256：", item.get("original_text_sha256", ""))
        findings = item.get("findings", [])
        if not findings:
            add_para(doc, "本次未记录问题；不表示该条款已被确认无风险。", first_indent=28)
        for finding in findings:
            render_finding(doc, finding, authorities)


def render_summary(doc: Document, data: dict[str, Any]) -> None:
    add_section_heading(doc, "三、风险汇总")
    review_items = data.get("review_items", [])
    findings = [item for clause in review_items for item in clause.get("findings", [])]
    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        level = finding.get("risk", {}).get("level", "low")
        counts[level] = counts.get(level, 0) + 1
    add_label_para(
        doc, "总体统计：",
        f"共审查 {len(review_items)} 条条款，记录 {len(findings)} 项审查发现；"
        f"其中高风险 {counts['high']} 项、中风险 {counts['medium']} 项、低风险 {counts['low']} 项。",
    )
    redlines = data.get("redline_instructions", [])
    add_label_para(
        doc, "红线指令：",
        f"已生成 {len(redlines)} 条变更指令，均未应用，未修改合同原文。",
    )
    if data.get("blocked"):
        add_para(doc, "本次审查存在阻断项，风险统计仅为筛查参考，须由执业律师核验后使用。", first_indent=28)
    if findings:
        for clause in review_items:
            heading = clause.get("heading", "")
            clause_id = clause.get("clause_id", "")
            for finding in clause.get("findings", []):
                risk = finding.get("risk", {})
                level = risk.get("level", "low")
                expression = risk.get("expression", "")
                add_label_para(
                    doc,
                    f"【{RISK_CN.get(level, level)}风险 · {EXPRESSION_CN.get(expression, expression)}】"
                    f"{heading}（{clause_id}；{finding.get('finding_id', '')}）：",
                    finding.get("issue", ""),
                )
    add_para(doc, "本报告由 AI 辅助生成，仅供学习参考，不得直接用于提交法院或对方当事人。", first_indent=28)
    add_para(doc, "使用前必须由专业执业律师逐项核验事实、法源与法律适用。", first_indent=28)


def render(data: dict[str, Any]) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    # Title: 思源宋体 18pt REGULAR, centered (not bold)
    add_para(doc, "合同审查报告", size=18, bold=True, align="center")
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）

    render_overview(doc, data)
    render_items(doc, data)
    render_summary(doc, data)
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染《合同审查报告》DOCX（思源宋体 14pt，行距固定 25pt）")
    parser.add_argument("--input", type=Path, required=True, help="审查结果 JSON 路径（review-output.schema.json）")
    parser.add_argument("--output", type=Path, required=True, help="输出 docx 路径（不得已存在）")
    args = parser.parse_args()

    data = load_input(args.input)
    if args.output.exists():
        raise FileExistsError(f"拒绝覆盖：{args.output}")

    doc = render(data)
    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py", "cn_legal_core_brand")
    with tempfile.TemporaryDirectory(prefix=".cn-contract-review-docx-") as temporary:
        raw_path = Path(temporary) / "raw.docx"
        doc.save(raw_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            docx_brand.brand_docx(
                raw_path, args.output,
                title="合同审查报告", subject="AI辅助生成，须由执业律师逐项核验",
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
