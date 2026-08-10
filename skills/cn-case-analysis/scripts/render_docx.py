#!/usr/bin/env python3
"""Render case-neutral analysis JSON into 案件中立分析报告 DOCX.

Typography follows the same contract as the reference renderers
(cn-complaint), adapted to the case-analysis report genre:
  - Body font Noto Serif SC（思源宋体，OFL 免费可商用）
  - Main title 18pt REGULAR (not bold), centered
  - Chapter headings 14pt bold, flush left; body 14pt regular
  - Fixed line spacing 25pt; first-line indent 28pt (2 chars)
  - Margins: left 25mm / right 20mm / top 30mm / bottom 20mm
  - Structure: 案件概况 → 事实来源 → 时间轴 → 争点 → 风险与待确认事项
  - Fields are mapped from the actual JSON; anything absent is reported
    as such — nothing is invented.
  - Compact brand header/footer via cn-legal-core docx_brand.brand_docx

Input contract: cn-case-analysis 输出（analysis.normalized.json 或
analysis-derived.json，schema_version 1.0），顶层含 parties / claims /
facts / issues / evidence / authorities / issue_analyses /
pending_confirmations / lawyer_judgments / domain_packs。

Usage:
    python3 render_docx.py --input analysis.normalized.json \
        --output <dir>/案件中立分析报告.docx
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

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
CN_LEGAL_CORE = SKILLS_ROOT / "cn-legal-core"
BODY_FONT = "Noto Serif SC"  # 思源宋体 OFL，免费可商用
DOC_TITLE = "案件中立分析报告"

CN_DIGITS = "一二三四五六七八九十"

# 状态/类型中文化映射（未列出的取值原样输出，不臆造含义）
FACT_STATUS = {"stated": "已载明", "user_confirmed": "用户已确认", "conflict": "存在冲突",
               "disputed": "有争议", "missing": "缺失"}
ISSUE_STATUS = {"disputed": "有争议", "open": "未决", "blocked": "待核验",
                "resolved": "已解决", "answered": "已回应"}
ELEMENT_STATUS = {"supported": "有支撑", "partially_supported": "部分有支撑",
                  "unsupported": "无支撑", "disputed": "有争议", "missing": "缺失",
                  "not_applicable": "不适用", "research_required": "待研究",
                  "lawyer_judgment_required": "待律师判断"}
POSITION_TYPE = {"assertion": "主张", "denial": "否认", "alternative": "备位主张",
                 "reservation": "保留意见"}
RISK_TYPE = {"fact_gap": "事实缺口", "evidence_gap": "证据缺口", "authority_gap": "法源缺口",
             "procedure_uncertainty": "程序不确定", "legal_uncertainty": "法律不确定",
             "strategy_choice": "策略选择"}
RISK_LEVEL = {"high": "高", "medium": "中", "low": "低", "unknown": "未知"}
FRAME = {"claim_right": "请求权", "defense": "抗辩", "procedure": "程序"}
ENTITY_TYPE = {"legal_person": "法人", "natural_person": "自然人",
               "other_organization": "其他组织", "sole_proprietorship": "个体工商户"}
REVIEW_STATUS = {"unreviewed": "未审查"}
VERIFY_STATUS = {"pending": "待核验", "in_progress": "核验中", "verified": "已核验"}
CLAIM_STATUS = {"stated": "已提出"}


def _cn(status_map: dict, key) -> str:
    """状态值中文化：无映射时原样输出，绝不编造含义。"""
    if key is None:
        return ""
    return status_map.get(key, str(key))


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
             align: str = "left", first_indent: float = 0.0):
    """正文段落：固定行距 25pt，无段前段后。"""
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


def add_heading(doc: Document, text: str, *, indent: float = 0.0):
    """章/节标题：14pt 加粗，固定行距 25pt。"""
    return add_para(doc, text, size=14, bold=True, first_indent=indent)


def add_label_para(doc: Document, label: str, content: str):
    """标签加粗、内容常规，同段呈现，首行缩进 28pt。"""
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
    """1 → 一，12 → 十二，21 → 二十一（诉请/条目中文编号）。"""
    if n <= 10:
        return CN_DIGITS[n - 1]
    tens, ones = divmod(n, 10)
    tens_char = CN_DIGITS[tens - 1] if tens > 1 else ""
    return f"{tens_char}十" + (CN_DIGITS[ones - 1] if ones else "")


def span_text(span: dict) -> str:
    """来源引文定位：SRC-001 第28段。"""
    source = span.get("source_id", "")
    paragraph = span.get("paragraph")
    page = span.get("page")
    position = ""
    if paragraph is not None:
        position = f"第{paragraph}段"
    elif page is not None:
        position = f"第{page}页"
    return f"{source}{' ' + position if position else ''}".strip()


def span_quote(span: dict) -> str:
    return span.get("quote", "")


def party_name_map(payload: dict) -> dict:
    return {p.get("party_id"): p.get("name", "") for p in payload.get("parties") or []}


def names_of(ids, name_map: dict) -> str:
    return "、".join(name_map.get(i, i) for i in ids if i) if ids else ""


def add_title(doc: Document) -> None:
    add_para(doc, DOC_TITLE, size=18, bold=True, align="center")
    doc.paragraphs[-1].paragraph_format.space_after = Pt(30)  # 标题段后间距（2026-08-10：不空行）


# ---------------------------------------------------------------- 一、案件概况
def render_overview(doc: Document, payload: dict) -> None:
    add_heading(doc, "一、案件概况")

    # 分析标识
    add_label_para(doc, "分析编号：", f"{payload.get('analysis_id', '')}　"
                   f"案号：{payload.get('matter_id', '')}")
    perspective = payload.get("analysis_perspective", "")
    add_label_para(doc, "分析视角：",
                   f"{'中立' if perspective == 'neutral' else perspective}　"
                   f"截止日期：{payload.get('as_of_date', '')}")
    if payload.get("schema_version"):
        add_label_para(doc, "数据契约：", f"schema_version {payload['schema_version']}")
    if payload.get("analysis_objective"):
        add_label_para(doc, "分析目的：", payload["analysis_objective"])

    # 案由与结论状态（analysis-derived.json 特有字段，缺失时跳过）
    cause = payload.get("cause_of_action_status")
    final = payload.get("final_outcome_status")
    if cause or final:
        cause_cn = {"not_selected_by_skill": "未由本 Skill 自动选择"}.get(cause, cause)
        final_cn = {"lawyer_independent_judgment_required": "待律师独立判断"}.get(final, final)
        add_label_para(doc, "案由状态：", f"{cause_cn}；结论状态：{final_cn}")
    coverage = payload.get("frame_coverage")
    if isinstance(coverage, dict) and coverage:
        parts = [f"{FRAME.get(k, k)}{'已覆盖' if v else '未覆盖'}" for k, v in coverage.items()]
        add_label_para(doc, "分析框架覆盖：", "；".join(parts))

    # 当事人
    parties = payload.get("parties") or []
    add_heading(doc, "（一）当事人", indent=28)
    if not parties:
        add_para(doc, "未提供当事人信息。", first_indent=28)
    for party in parties:
        roles = "、".join(party.get("procedural_roles") or [])
        entity = _cn(ENTITY_TYPE, party.get("entity_type"))
        meta = "、".join(part for part in (roles, entity) if part)
        line = f"{party.get('name', '')}（{meta}）" if meta else party.get("name", "")
        add_label_para(doc, f"{party.get('party_id', '')}　", line)
        for span in party.get("source_spans") or []:
            quote = span_quote(span)
            add_para(doc, f"来源：{span_text(span)}：{quote}", first_indent=28)

    # 诉请
    claims = payload.get("claims") or []
    add_heading(doc, "（二）诉请", indent=28)
    if not claims:
        add_para(doc, "未提供诉请信息。", first_indent=28)
    name_map = party_name_map(payload)
    for claim in claims:
        order = claim.get("order") or 0
        text = claim.get("text_verbatim", "")
        liable = names_of(claim.get("liable_party_ids") or [], name_map)
        status = _cn(CLAIM_STATUS, claim.get("status"))
        amount = claim.get("amount")
        currency = claim.get("currency", "")
        extra = []
        if amount is not None:
            extra.append(f"{currency} {amount:,}")
        if liable:
            extra.append(f"责任方：{liable}")
        if status:
            extra.append(f"状态：{status}")
        suffix = f"（{'；'.join(extra)}）" if extra else ""
        add_para(doc, f"{cn_number(order) if order else '?'}、{text}{suffix}", first_indent=28)

    # 证据清单（仅登记审查状态，不认定三性）
    evidence = payload.get("evidence") or []
    add_heading(doc, "（三）证据清单", indent=28)
    if not evidence:
        add_para(doc, "未提供证据信息。", first_indent=28)
    for item in evidence:
        review = _cn(REVIEW_STATUS, item.get("authenticity"))
        verify = _cn(VERIFY_STATUS, item.get("verification_status"))
        state = f"三性审查状态：{review}；核验状态：{verify}"
        add_label_para(doc, f"{item.get('evidence_id', '')}　",
                       f"{item.get('name', '')}（{state}）")

    # 法律依据与领域包
    authorities = payload.get("authorities") or []
    add_heading(doc, "（四）法律依据", indent=28)
    if not authorities:
        add_para(doc, "输入未提供法律依据（authorities）条目。", first_indent=28)
    for authority in authorities:
        add_para(doc, authority.get("text") or json.dumps(authority, ensure_ascii=False),
                 first_indent=28)
    for pack in payload.get("domain_packs") or []:
        add_para(doc,
                 f"已加载领域包：{pack.get('pack_id', '')}（版本 {pack.get('version', '')}）",
                 first_indent=28)


# ---------------------------------------------------------------- 二、事实来源
def render_facts(doc: Document, payload: dict) -> None:
    add_heading(doc, "二、事实来源")
    facts = payload.get("facts") or []
    if not facts:
        add_para(doc, "未提供事实信息。", first_indent=28)
        return
    for fact in facts:
        status = _cn(FACT_STATUS, fact.get("status"))
        label = f"{fact.get('fact_id', '')}　{fact.get('field', '')}"
        if status:
            label += f"（{status}）"
        add_label_para(doc, f"{label}：", fact.get("raw_value", ""))
        for span in fact.get("source_spans") or []:
            quote = span_quote(span)
            add_para(doc, f"来源：{span_text(span)}：{quote}", first_indent=28)


# ---------------------------------------------------------------- 三、时间轴
def render_timeline(doc: Document, payload: dict) -> None:
    add_heading(doc, "三、时间轴")
    timeline = payload.get("timeline")
    if not timeline:
        add_para(doc,
                 "输入数据（schema_version 1.0）未提供独立时间轴（timeline）数据。"
                 "关键时间点见“二、事实来源”各条目（如合同签订、竣工验收、"
                 "结算确认、催告、起诉、判决等）。",
                 first_indent=28)
        return
    for item in timeline:
        date = item.get("date") or item.get("time") or ""
        text = item.get("text") or item.get("description") or item.get("event") or ""
        add_para(doc, f"{date}　{text}", first_indent=28)


# ---------------------------------------------------------------- 四、争点
def render_positions(doc: Document, positions: list, name_map: dict) -> None:
    """各方主张：当事人（主张类型）：陈述。"""
    for position in positions:
        party = name_map.get(position.get("party_id"), position.get("party_id"))
        ptype = _cn(POSITION_TYPE, position.get("position_type"))
        add_label_para(doc, f"{party}（{ptype}）：", position.get("statement", ""))


def render_elements(doc: Document, elements: list) -> None:
    """要件：名称（状态）：工作备注 + 反方意见。"""
    for element in elements:
        estatus = _cn(ELEMENT_STATUS, element.get("status"))
        add_label_para(doc, f"要件：{element.get('name', '')}（{estatus}）：",
                       element.get("working_note", ""))
        for opposing in element.get("opposing_arguments") or []:
            add_para(doc, f"反方意见：{opposing}", first_indent=28)


def render_issue_tree(doc: Document, nodes: list, counter: list,
                      elements_by_issue: dict, positions_by_issue: dict,
                      name_map: dict) -> None:
    """analysis-derived.json 的 issue_tree 视图：递归渲染争点树。"""
    for node in nodes:
        counter[0] += 1
        issue_id = node.get("issue_id", "")
        frame = _cn(FRAME, node.get("frame"))
        status = _cn(ISSUE_STATUS, node.get("issue_status"))
        meta = "｜".join(part for part in ("争点", frame, status) if part)
        add_heading(doc, f"（{cn_number(counter[0])}）{issue_id}【{meta}】", indent=28)
        add_para(doc, node.get("question", ""), first_indent=28)
        render_positions(doc, positions_by_issue.get(issue_id) or [], name_map)
        render_elements(doc, elements_by_issue.get(issue_id) or [])
        children = node.get("children") or []
        if children:
            add_para(doc, "子争点：", first_indent=28)
            render_issue_tree(doc, children, counter, elements_by_issue,
                              positions_by_issue, name_map)


def render_issues(doc: Document, payload: dict) -> None:
    add_heading(doc, "四、争点")
    issues = payload.get("issues") or []
    issues_by_id = {i.get("issue_id"): i for i in issues}
    analyses = {a.get("issue_id"): a for a in payload.get("issue_analyses") or []}
    name_map = party_name_map(payload)

    elements_by_issue = {}
    positions_by_issue = {}
    for analysis in analyses.values():
        elements_by_issue[analysis.get("issue_id")] = analysis.get("elements") or []
        positions_by_issue[analysis.get("issue_id")] = analysis.get("positions") or []
    # derived 视图补充：element_matrix / party_positions（按 issue_id 归组）
    for entry in payload.get("element_matrix") or []:
        elements_by_issue.setdefault(entry.get("issue_id"), []).append(entry)
    for entry in payload.get("party_positions") or []:
        positions_by_issue.setdefault(entry.get("issue_id"), []).append(entry)

    # 按 issue_analyses.order 排序渲染；缺失分析对象的争点附加在末尾
    ordered = sorted(analyses.values(), key=lambda a: a.get("order", 0))
    seen = {a.get("issue_id") for a in ordered}
    ordered += [i for i in issues if i.get("issue_id") not in seen]

    if not ordered:
        tree = payload.get("issue_tree")
        if tree:
            render_issue_tree(doc, tree, [0], elements_by_issue,
                              positions_by_issue, name_map)
            return
        add_para(doc, "未提供争点信息。", first_indent=28)
        return

    for index, item in enumerate(ordered, 1):
        issue_id = item.get("issue_id", "")
        core = issues_by_id.get(issue_id) or item  # 核心争点字段在 issues 中
        analysis = analyses.get(issue_id, {})
        parent = analysis.get("parent_issue_id") or core.get("parent_issue_id")
        frame = _cn(FRAME, analysis.get("frame"))
        status = _cn(ISSUE_STATUS, core.get("status"))
        tag = "子争点" if parent else "争点"
        meta = "｜".join(part for part in (tag, frame, status) if part)
        if parent:
            meta += f"｜父争点：{parent}"
        add_heading(doc, f"（{cn_number(index)}）{issue_id}【{meta}】", indent=28)
        add_para(doc, core.get("question", ""), first_indent=28)
        if core.get("burden_of_proof"):
            add_label_para(doc, "举证责任：", core["burden_of_proof"])
        render_positions(doc, positions_by_issue.get(issue_id) or [], name_map)
        render_elements(doc, elements_by_issue.get(issue_id) or [])


# ---------------------------------------------------- 五、风险与待确认事项
def collect(payload: dict, nested_key: str, top_key: str) -> list:
    """合并顶层清单与 issue_analyses 内清单（按 id 去重，顶层优先）。"""
    merged = {}
    for item in payload.get(top_key) or []:
        merged[item.get("id") or item.get("risk_id") or item.get("research_id")] = item
    for analysis in payload.get("issue_analyses") or []:
        for item in analysis.get(nested_key) or []:
            key = item.get("id") or item.get("risk_id") or item.get("research_id")
            merged.setdefault(key, item)
    return list(merged.values())


def render_risks(doc: Document, payload: dict) -> None:
    risks = collect(payload, "risks", "risks")
    add_heading(doc, "五、风险与待确认事项")
    add_heading(doc, "（一）风险清单", indent=28)
    if not risks:
        add_para(doc, "未登记风险条目。", first_indent=28)
    for index, risk in enumerate(risks, 1):
        rtype = _cn(RISK_TYPE, risk.get("risk_type"))
        level = _cn(RISK_LEVEL, risk.get("level"))
        add_para(doc,
                 f"{cn_number(index)}、{risk.get('risk_id', '')}"
                 f"（{rtype}｜{level}）：{risk.get('description', '')}",
                 first_indent=28)
        if risk.get("next_action"):
            add_label_para(doc, "下一步：", risk["next_action"])


def render_confirmations(doc: Document, payload: dict) -> None:
    confirmations = payload.get("pending_confirmations") or []
    add_heading(doc, "（二）待确认事项", indent=28)
    if not confirmations:
        add_para(doc, "无待确认事项。", first_indent=28)
    for index, confirm in enumerate(confirmations, 1):
        blocking = "阻断" if confirm.get("blocking") else "非阻断"
        add_para(doc,
                 f"{cn_number(index)}、{confirm.get('confirmation_id', '')}"
                 f"（{blocking}）：{confirm.get('question', '')}",
                 first_indent=28)


def render_research(doc: Document, payload: dict) -> None:
    items = collect(payload, "research_items", "research_items")
    priority_cn = {"high": "高", "medium": "中", "low": "低"}
    status_cn = {"open": "待研", "in_progress": "进行中", "verified": "已核验"}
    add_heading(doc, "（三）待研究事项", indent=28)
    if not items:
        add_para(doc, "无待研究事项。", first_indent=28)
    for index, item in enumerate(items, 1):
        add_para(doc,
                 f"{cn_number(index)}、{item.get('research_id', '')}："
                 f"{item.get('question', '')}"
                 f"（优先级：{priority_cn.get(item.get('priority', ''), item.get('priority', ''))}；"
                 f"状态：{status_cn.get(item.get('status', ''), item.get('status', ''))}）",
                 first_indent=28)


def render_judgments(doc: Document, payload: dict) -> None:
    judgments = payload.get("lawyer_judgments") or []
    add_heading(doc, "（四）待律师独立判断", indent=28)
    if not judgments:
        add_para(doc, "无待律师判断事项。", first_indent=28)
    for index, judgment in enumerate(judgments, 1):
        status = {"pending": "待判断", "provided": "已提供"}.get(judgment.get("status"),
                                                                judgment.get("status", ""))
        add_para(doc, f"{cn_number(index)}、{judgment.get('judgment_id', '')}"
                 f"（{status}）：{judgment.get('question', '')}",
                 first_indent=28)
        if judgment.get("content"):
            add_label_para(doc, "律师判断：", judgment["content"])
            reviewer = judgment.get("reviewed_by", "")
            reviewed_at = judgment.get("reviewed_at", "")
            add_label_para(doc, "复核：", f"{reviewer}　{reviewed_at}".strip())


def add_closing(doc: Document) -> None:
    add_para(doc, "", first_indent=28)
    add_para(doc, "本报告系中立分析复核底稿：案由未由本 Skill 自动选择，"
             "案件结论待执业律师独立判断，不构成法律意见。",
             first_indent=28)


def render(payload: dict) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)

    add_title(doc)
    render_overview(doc, payload)
    render_facts(doc, payload)
    render_timeline(doc, payload)
    render_issues(doc, payload)
    render_risks(doc, payload)
    render_confirmations(doc, payload)
    render_research(doc, payload)
    render_judgments(doc, payload)
    add_closing(doc)
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染《案件中立分析报告》DOCX（思源宋体参考排版）")
    parser.add_argument("--input", type=Path, required=True,
                        help="cn-case-analysis 输出 JSON（normalized 或 derived）路径")
    parser.add_argument("--output", type=Path, required=True, help="输出 docx 路径（不得已存在）")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"[ERROR] 输入文件不存在：{args.input}", file=sys.stderr)
        return 1
    if args.output.exists():
        raise FileExistsError(f"拒绝覆盖：{args.output}")

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[ERROR] 输入 JSON 解析失败：{exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("[ERROR] 输入 JSON 顶层必须是对象", file=sys.stderr)
        return 1
    # 兼容“外层包装”形式（如 {"analysis": {...}}）
    if "analysis" in payload and "parties" not in payload:
        payload = payload["analysis"]

    doc = render(payload)

    docx_brand = load_module(CN_LEGAL_CORE / "scripts" / "docx_brand.py",
                             "cn_legal_core_brand")
    # 兼容性修补：docx_brand 新版页眉逻辑用到 WD_LINE_SPACING/Pt 但 require_docx()
    # 未导入（cn-legal-core 共享模块的既有缺陷，不在本任务范围内修复）。
    if not hasattr(docx_brand, "WD_LINE_SPACING"):
        docx_brand.WD_LINE_SPACING = WD_LINE_SPACING
    if not hasattr(docx_brand, "Pt"):
        docx_brand.Pt = Pt
    with tempfile.TemporaryDirectory(prefix=".cn-case-analysis-docx-") as temporary:
        raw_path = Path(temporary) / "raw.docx"
        doc.save(raw_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            docx_brand.brand_docx(
                raw_path, args.output,
                title=DOC_TITLE, subject="AI辅助生成，须由执业律师逐项核验",
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
