#!/usr/bin/env python3
"""
cn-procedure references 模板生成器（终极版）
设计原则：
- 1.2 倍行距（紧凑）
- 仅使用免费可商用的思源字体
- A4 标准页边距 2.54cm
- 统一页脚：居中"第 N 页 · AIOffice 职场通关"
- 规范化占位符 {{ ... }}，便于 Skill 自动填写
- 合同精简（4-5 页）
"""
import re
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from PIL import Image


# ============================================================
# 常量
# ============================================================
SKILL_DIR = Path(__file__).resolve().parent.parent
HORIZONTAL_LOGO = SKILL_DIR / "assets" / "brand" / "header-logo.png"
FOOTER_LOGO = SKILL_DIR / "assets" / "brand" / "footer-logo.png"
if not HORIZONTAL_LOGO.is_file() or not FOOTER_LOGO.is_file():
    raise FileNotFoundError("缺少 AIOffice 页眉或页脚 Logo 发布副本")

TEMP_DIR = Path(tempfile.gettempdir()) / "aioffice-cn-procedure"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# 自动裁切 Logo 上下空白（去白边）
LOGO_CROPPED = TEMP_DIR / "horiz_logo_cropped.png"
if not LOGO_CROPPED.exists():
    img = Image.open(HORIZONTAL_LOGO)
    if img.mode == 'RGBA':
        bbox = img.split()[3].getbbox()
        if bbox:
            img = img.crop(bbox)
    img.save(LOGO_CROPPED, "PNG", optimize=True)
LOGO_RESIZED = TEMP_DIR / "horiz_logo_240.png"
if not LOGO_RESIZED.exists():
    img = Image.open(LOGO_CROPPED)
    w, h = img.size
    img.resize((240, int(h * 240 / w)), Image.LANCZOS).save(LOGO_RESIZED, "PNG", optimize=True)

PAGE_MARGIN_CM = 2.54
DOCUMENT_AUTHOR = "AIOffice职场通关-excel1949"
DOCUMENT_BRAND = "AIOffice职场通关"
DOCUMENT_COMMENT = "AI辅助生成，须由执业律师逐项核验"
APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

# 免费可商用字体：正文与标题统一使用仿宋（法院文书标准），西文同字族回退。
FONT_BODY_CN = "Noto Serif SC"  # 思源宋体 OFL（替代系统仿宋防侵权）
FONT_TITLE_CN = "Noto Sans SC"  # 思源黑体 OFL
FONT_LATIN = "Noto Serif SC"

# 标题字体（粗体）
FONT_TITLE_CN_BOLD = "Noto Sans SC"

SIZE_TITLE = 18
SIZE_H1 = 14
SIZE_H2 = 14
SIZE_BODY = 14

COLOR_BLACK = RGBColor(0, 0, 0)  # 专业法律文书必须纯黑
COLOR_GRAY = RGBColor(0x6B, 0x6B, 0x6B)

# 行距：固定 25pt（对齐法院起诉状参考排版）
LINE_SPACING = Pt(25)
LINE_SPACING_RULE = WD_LINE_SPACING.EXACTLY


# ============================================================
# 字体设置（核心 helper）
# ============================================================

def _set_run_font(run, font_cn=None, size=None):
    """安全设置 run 的字体（CJK + 拉丁）和字号
    font_cn: 主字体名。
    """
    if size is not None:
        run.font.size = Pt(size)
    # 设置 CJK 字体到 rPr
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:ascii'), FONT_LATIN)
    rFonts.set(qn('w:hAnsi'), FONT_LATIN)
    cn = font_cn or FONT_BODY_CN
    rFonts.set(qn('w:eastAsia'), cn)
    rFonts.set(qn('w:cs'), FONT_LATIN)


def _font_title(font_size=None):
    """标题字体（思源黑体）"""
    return (FONT_TITLE_CN, font_size)


def _font_body(font_size=None):
    """正文字体（鸿蒙 + 仿宋 fallback）"""
    # 在 w:rFonts 中用主字体，其他字体放入 fallback chain
    return (FONT_BODY_CN, font_size)


# ============================================================
# 页面/样式
# ============================================================

def set_page_setup(doc):
    """A4 + 2.54cm 页边距"""
    for sec in doc.sections:
        sec.page_height = Cm(29.7)
        sec.page_width = Cm(21.0)
        sec.top_margin = Cm(PAGE_MARGIN_CM)
        sec.bottom_margin = Cm(PAGE_MARGIN_CM)
        sec.left_margin = Cm(PAGE_MARGIN_CM)
        sec.right_margin = Cm(PAGE_MARGIN_CM)
        sec.header_distance = Cm(1.0)
        sec.footer_distance = Cm(1.0)


def set_default_styles(doc):
    """Normal 样式：10.5pt + 1.2 倍行距 + 思源黑体。"""
    style = doc.styles['Normal']
    style.font.size = Pt(SIZE_BODY)
    style.font.name = FONT_LATIN
    pf = style.paragraph_format
    pf.line_spacing = LINE_SPACING
    pf.line_spacing_rule = LINE_SPACING_RULE

    # 设置默认字体。
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:ascii'), FONT_LATIN)
    rFonts.set(qn('w:hAnsi'), FONT_LATIN)
    # 使用 w:eastAsia 放主字体；Word 会按系统安装顺序 fallback
    rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)
    rFonts.set(qn('w:cs'), FONT_LATIN)


def add_header_with_logo(doc):
    """页眉：左对齐横版 Logo（3.5cm 宽，已裁切上下白边）"""
    section = doc.sections[0]
    header = section.header
    hdr_elem = header._element
    for p in list(hdr_elem.findall(qn('w:p'))):
        hdr_elem.remove(p)

    new_p = OxmlElement('w:p')
    pPr = OxmlElement('w:pPr')
    jc = OxmlElement('w:jc')
    jc.set(qn('w:val'), 'left')
    pPr.append(jc)
    spacing = OxmlElement('w:spacing')
    spacing.set(qn('w:after'), '40')
    spacing.set(qn('w:before'), '0')
    pPr.append(spacing)
    new_p.append(pPr)
    hdr_elem.append(new_p)

    # 加 logo（左对齐，3.5cm 宽）
    from docx.text.paragraph import Paragraph
    p = Paragraph(new_p, header)
    run = p.add_run()
    run.add_picture(str(LOGO_RESIZED), width=Cm(3.5))


def add_brand_footer(doc):
    """页脚：居中放置 Logo、品牌名和页码。"""
    section = doc.sections[0]
    footer = section.footer
    ftr_elem = footer._element
    for p in list(ftr_elem.findall(qn('w:p'))):
        ftr_elem.remove(p)

    new_p = OxmlElement('w:p')
    pPr = OxmlElement('w:pPr')
    jc = OxmlElement('w:jc')
    jc.set(qn('w:val'), 'center')
    pPr.append(jc)
    spacing = OxmlElement('w:spacing')
    spacing.set(qn('w:before'), '60')
    spacing.set(qn('w:after'), '0')
    pPr.append(spacing)
    new_p.append(pPr)
    ftr_elem.append(new_p)

    from docx.text.paragraph import Paragraph
    p = Paragraph(new_p, footer)

    logo_run = p.add_run()
    logo_run.add_picture(str(FOOTER_LOGO), width=Cm(1.6))

    r1 = p.add_run("  AIOffice职场通关  ·  第 ")
    _set_run_font(r1, font_cn=FONT_BODY_CN, size=9)
    r1.font.color.rgb = COLOR_BLACK

    # PAGE field
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')
    r_fld1 = p.add_run()
    _set_run_font(r_fld1, font_cn=FONT_BODY_CN, size=9)
    r_fld1.font.color.rgb = COLOR_BLACK
    r_fld1._element.append(fldChar1)

    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = ' PAGE '
    r_instr = p.add_run()
    _set_run_font(r_instr, font_cn=FONT_BODY_CN, size=9)
    r_instr.font.color.rgb = COLOR_BLACK
    r_instr._element.append(instr)

    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'end')
    r_fld2 = p.add_run()
    _set_run_font(r_fld2, font_cn=FONT_BODY_CN, size=9)
    r_fld2.font.color.rgb = COLOR_BLACK
    r_fld2._element.append(fldChar2)

    r2 = p.add_run(" 页")
    _set_run_font(r2, font_cn=FONT_BODY_CN, size=9)
    r2.font.color.rgb = COLOR_BLACK


def make_base_doc():
    """创建带页眉（Logo）与 A4 设置的基础 doc；2026-08-09 规范：页脚不放内容"""
    doc = Document()
    set_page_setup(doc)
    set_default_styles(doc)
    add_header_with_logo(doc)
    return doc


# ============================================================
# 段落 helper（精简易用）
# ============================================================

def add_para(doc, text, *, size=SIZE_BODY, bold=False, align=None,
             indent=False, color=None, space_before=0, space_after=2):
    """添加段落：1.2 倍行距（鸿蒙字体 fallback 仿宋/思源黑体）"""
    p = doc.add_paragraph()
    p.alignment = align if align else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    if indent and text:
        # 首行缩进 = 2 字符
        p.paragraph_format.first_line_indent = Pt(SIZE_BODY * 2)

    if text is not None:
        run = p.add_run(text)
        _set_run_font(run, font_cn=FONT_BODY_CN, size=size)
        if bold:
            run.bold = True
        if color:
            run.font.color.rgb = color
    return p


def add_title(doc, text, size=SIZE_TITLE):
    """居中标题（思源黑体）"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run(text)
    _set_run_font(run, font_cn=FONT_TITLE_CN, size=size)
    run.bold = True
    return p


def add_h1(doc, text):
    """一级标题（思源黑体）"""
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    _set_run_font(run, font_cn=FONT_TITLE_CN, size=SIZE_H1)
    run.bold = True
    return p


# ============================================================
# 表格 helper
# ============================================================

def add_table(doc, title, rows, label_width_cm=4.5, value_width_cm=11.0):
    """添加带标题的两列表格"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
    run = p.add_run(title)
    _set_run_font(run, font_cn=FONT_TITLE_CN, size=SIZE_H1)
    run.bold = True

    table = doc.add_table(rows=len(rows), cols=2)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    for i, (label, placeholder) in enumerate(rows):
        cell_l = table.cell(i, 0)
        cell_l.text = ""
        p_l = cell_l.paragraphs[0]
        p_l.paragraph_format.line_spacing = LINE_SPACING
        p_l.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
        run = p_l.add_run(label)
        _set_run_font(run, font_cn=FONT_TITLE_CN, size=SIZE_BODY)
        run.bold = True
        cell_l.width = Cm(label_width_cm)

        cell_r = table.cell(i, 1)
        cell_r.text = ""
        p_r = cell_r.paragraphs[0]
        p_r.paragraph_format.line_spacing = LINE_SPACING
        p_r.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
        if placeholder:
            run = p_r.add_run(placeholder)
            _set_run_font(run, font_cn=FONT_BODY_CN, size=SIZE_BODY)
        cell_r.width = Cm(value_width_cm)
    return table


def save(doc, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    props = doc.core_properties
    props.author = DOCUMENT_AUTHOR
    props.last_modified_by = DOCUMENT_AUTHOR
    props.title = path.stem
    props.subject = "中国律师程序文书模板"
    props.category = "AIOffice职场通关法律Skill"
    props.comments = DOCUMENT_COMMENT
    doc.save(str(path))
    with zipfile.ZipFile(path, "r") as source:
        members = {name: source.read(name) for name in source.namelist() if not name.endswith("/")}
    app_name = "docProps/app.xml"
    root = ET.fromstring(members[app_name])
    company = root.find(f"{{{APP_NS}}}Company")
    if company is None:
        company = ET.SubElement(root, f"{{{APP_NS}}}Company")
    company.text = DOCUMENT_BRAND
    members[app_name] = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as destination:
        for name, content in sorted(members.items()):
            destination.writestr(name, content)
    temporary.replace(path)


# ============================================================
# 标准占位符
# ============================================================
# {{client_name}} / {{client_id}} / {{client_address}} / {{client_phone}}
# {{opponent_name}} / {{case_cause}} / {{case_court}} / {{case_number}}
# {{lawyer_name}} / {{lawyer_license}} / {{firm_name}} / {{firm_address}} / {{firm_phone}}
# {{fee_amount}} / {{fee_amount_cn}}
# {{disputed_amount}} / {{sign_date}}
# 注：用 Skill 自动填写时按上述标识替换为实际值


# ============================================================
# 1) 所函
# ============================================================

def make_suohan(out_path, kind):
    doc = make_base_doc()
    title = "律 师 事 务 所 函" if kind == "民事" else "律 师 事 务 所 函（刑 事）"
    add_title(doc, title)

    add_para(doc, "编 号：【{{doc_number}}】", indent=False)
    add_para(doc, "{{case_court}}：")
    add_para(doc, "")

    if kind == "民事":
        add_para(doc,
            "贵院受理的 {{client_name}} 与 {{opponent_name}} {{case_cause}} 一案，"
            "本所接受 {{client_name}} 委托，指派 {{lawyer_name}} 律师担任其诉讼代理人。",
            indent=True)
    else:
        add_para(doc,
            "贵院/处办理的 {{criminal_subject_name}} 涉嫌 {{case_cause}} 一案，"
            "本所指派 {{lawyer_name}} 律师担任本案 {{criminal_subject_name}} 的 {{criminal_role|辩护人/诉讼代理人}}。",
            indent=True)

    add_para(doc, "")
    add_para(doc, "特此函告。")
    add_para(doc, "")
    add_para(doc, "")

    # 右下角签章
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
    run = p.add_run("{{firm_name}}")
    _set_run_font(run, font_cn=FONT_BODY_CN, size=SIZE_BODY)
    run.bold = True

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.line_spacing = LINE_SPACING
    p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
    run = p.add_run("{{sign_date}}")
    _set_run_font(run, font_cn=FONT_BODY_CN, size=SIZE_BODY)

    if kind == "刑事":
        add_para(doc, "")
        add_para(doc, "附：授权委托书一份。", indent=False)

    save(doc, out_path)
    print(f"  ✓ {Path(out_path).name}")


# ============================================================
# 2) 授权委托书
# ============================================================

def make_authorization_letter(out_path, scope, special_items=None, criminal_stages=None, civil_relative_mode=False):
    """
    生成授权委托书
    scope: "民事" / "刑事" / "行政"
    special_items: 特别授权枚举列表（可选）
    civil_relative_mode: True = 民事-亲属关系（公民受托人，非律师）
    """
    doc = make_base_doc()

    add_title(doc, "授 权 委 托 书")

    # 委托人信息（通用）
    add_para(doc, "委托人：{{client_name}}", indent=False)
    add_para(doc, "身份证号：{{client_id}}", indent=False)
    add_para(doc, "地址：{{client_address}}    电话：{{client_phone}}", indent=False)
    add_para(doc, "")

    if civil_relative_mode:
        # 亲属关系模式：受托人是公民（非律师），用身份证；与委托人关系（如夫妻/父子/兄妹等）
        add_para(doc, "受委托人：{{agent_name}}（公民，非执业律师）", indent=False)
        add_para(doc, "身份证号：{{agent_id}}", indent=False)
        add_para(doc, "联系电话：{{agent_phone}}", indent=False)
        add_para(doc, "与委托人关系：系{{client_name}}的{{relationship|配偶/成年子女/父母/兄弟姐妹/祖父母/外祖父母/其他近亲属}}",
                 indent=False)
        add_para(doc, "")

        law = "《中华人民共和国民事诉讼法》第六十一条（当事人的近亲属或者工作人员可以被委托为诉讼代理人）"
    else:
        # 标准模式：受托人是律师
        add_para(doc, "受委托人：{{lawyer_name}} 律师", indent=False)
        add_para(doc, "执业机构：{{firm_name}}    执业证号：{{lawyer_license}}", indent=False)
        add_para(doc, "")

        if scope.startswith("民事") or scope == "刑事亲属":
            law = "《中华人民共和国民事诉讼法》第六十一条、第六十二条"
        elif scope == "刑事":
            law = "《中华人民共和国刑事诉讼法》第三十三条"
        else:
            law = "《中华人民共和国行政诉讼法》第三十一条及《中华人民共和国民事诉讼法》关于授权委托的相关规定"

    if scope == "刑事":
        add_para(doc,
            "委托人 {{client_name}} 现委托 {{lawyer_name}} 律师，在 {{criminal_subject_name}} "
            "涉嫌 {{case_cause}} 一案中担任 {{criminal_role|辩护人/诉讼代理人}}。"
            "委托事项与阶段依据《中华人民共和国刑事诉讼法》第三十三条等现行规定明确如下：",
            indent=True)
    elif civil_relative_mode:
        add_para(doc,
            "现委托 {{agent_name}}（{{agent_name}} 系 {{client_name}} 的近亲属）"
            "为 {{client_name}} 与 {{opponent_name}} 之间因 {{case_cause}} 引发的诉讼一案中的"
            "诉讼代理人。",
            indent=True)
    else:
        add_para(doc,
            "现委托 {{lawyer_name}} 律师在 {{client_name}} 与 {{opponent_name}} 之间"
            "因 {{case_cause}} 引发的法律事务中担任 {{client_name}} 的代理人。",
            indent=True)

    if scope != "刑事":
        add_para(doc, "代理事项和权限：{{authorization_scope_text}}。", indent=True)
        add_para(doc, "委托期限：{{authorization_period}}", indent=False)

    # 刑事阶段（仅刑事版）
    if criminal_stages:
        add_para(doc, "")
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = LINE_SPACING
        p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run("辩护阶段（请填写对应编号，可多选）：")
        _set_run_font(run, font_cn=FONT_TITLE_CN, size=SIZE_H2)
        run.bold = True

        for i, stage in enumerate(criminal_stages, 1):
            # stage 形如 "侦查阶段：会见、申请变更强制措施等"
            add_para(doc, f"（{i}）{stage}", indent=False)

        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = LINE_SPACING
        p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run("委托人授权阶段（请填写对应编号，可多选）：")
        _set_run_font(run, font_cn=FONT_TITLE_CN, size=SIZE_BODY)
        run.bold = True

        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = LINE_SPACING
        p.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run("{{criminal_stages|（1）（2）...|按编号填}}")
        _set_run_font(run, font_cn=FONT_BODY_CN, size=SIZE_BODY)
        run.bold = True

    # 签署栏与正文保持同页；避免空白段把日期单独挤到下一页。
    if scope == "刑事":
        add_para(doc, "委托人（签名/捺印）：__________________", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
        add_para(doc, "日 期：_______ 年 _______ 月 _______ 日", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    else:
        add_para(doc, "委托人（签名/盖章）：{{client_name}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
        add_para(doc, "{{sign_date}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)

    save(doc, out_path)
    print(f"  ✓ {Path(out_path).name}")


def make_organization_employee_authorization(out_path):
    """法人或非法人组织委托本单位工作人员参加民事诉讼。"""
    doc = make_base_doc()
    add_title(doc, "授 权 委 托 书")
    add_para(doc, "委托人：{{client_name}}", indent=False)
    add_para(doc, "统一社会信用代码：{{client_credit_code}}", indent=False)
    add_para(doc, "住所地：{{client_address}}", indent=False)
    add_para(
        doc,
        "法定代表人/主要负责人：{{client_legal_rep}}    职务：{{client_legal_rep_title}}",
        indent=False,
    )
    add_para(doc, "")
    add_para(doc, "受委托人：{{employee_name}}    身份证号：{{employee_id}}", indent=False)
    add_para(
        doc,
        "工作单位：{{client_name}}    职务：{{employee_title}}    联系电话：{{employee_phone}}",
        indent=False,
    )
    add_para(doc, "")
    add_para(
        doc,
        "现委托上述受委托人在本单位与 {{opponent_name}} 因 {{case_cause}} 一案中，"
        "作为本单位的诉讼代理人。",
        indent=True,
    )
    add_para(doc, "代理事项和权限：{{authorization_scope_text}}。", indent=True)
    add_para(doc, "")
    add_para(doc, "委托期限：{{authorization_period}}", indent=False)
    add_para(doc, "")
    add_para(doc, "委托人（盖章）：{{client_name}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(
        doc,
        "法定代表人/主要负责人（签名）：{{client_legal_rep}}",
        indent=False,
        align=WD_ALIGN_PARAGRAPH.RIGHT,
    )
    add_para(doc, "{{sign_date}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    save(doc, out_path)
    print(f"  ✓ {Path(out_path).name}")


# ============================================================
# 3) 委托代理合同（精简，4-5 页）
# ============================================================

def make_contract(out_path, kind):
    doc = make_base_doc()

    titles = {
        "民事": "民 事 委 托 代 理 合 同",
        "风险代理": "委 托 代 理 合 同（风险代理）",
        "刑事": "刑 事 委 托 代 理 合 同",
        "行政": "行 政 委 托 代 理 合 同",
        "执行": "委 托 代 理 合 同（执行阶段）",
    }
    add_title(doc, titles[kind])

    add_para(doc, "甲方（委托人）：{{client_name}}", indent=False)
    add_para(doc, "身份证号/统一社会信用代码：{{client_id}}", indent=False)
    add_para(doc, "地址：{{client_address}}    电话：{{client_phone}}", indent=False)
    add_para(doc, "")
    add_para(doc, "乙方（受托人）：{{firm_name}}", indent=False)
    add_para(doc, "地址：{{firm_address}}    电话：{{firm_phone}}", indent=False)
    add_para(doc, "")

    # 前言
    if kind == "刑事":
        intro = (
            "甲方因 {{criminal_subject_name}} 涉嫌 {{case_cause}} 一案，委托乙方提供刑事法律服务。"
            "依据《刑事诉讼法》《律师法》，达成如下协议。"
        )
    elif kind == "行政":
        intro = (
            "甲方因与 {{opponent_name}}（行政机关）之间 {{case_cause}} 争议，委托乙方代理。"
            "依据《行政诉讼法》《律师法》，达成如下协议。"
        )
    elif kind == "执行":
        intro = (
            "甲方因 {{case_cause}} 执行案件，委托乙方提供代理服务。"
            "依据《民事诉讼法》《律师法》，达成如下协议。"
        )
    else:
        intro = (
            "甲方因 {{case_cause}} 事宜，委托乙方代理相关法律事务。"
            "依据《民法典》《律师法》，达成如下协议。"
        )
    add_para(doc, intro, indent=True)

    # 第一条
    add_h1(doc, "第一条 委托事项")
    if kind == "执行":
        add_para(doc,
            "乙方接受甲方委托，指派 {{lawyer_name}} 律师在下列案件中担任甲方代理人：",
            indent=True)
        add_para(doc, "（一）执行依据：{{execution_basis}}　　（二）被执行人：{{opponent_name}}",
                 indent=True)
        add_para(doc, "（三）执行法院：{{case_court}}　　（四）执行标的：人民币 {{disputed_amount}} 元",
                 indent=True)
        add_para(doc, "（五）甲方应如实提供被执行人可供执行的财产线索（银行账户、不动产、车辆、投资权益等）。",
                 indent=True)
    elif kind == "刑事":
        add_para(doc,
            "乙方接受甲方委托，指派 {{lawyer_name}} 律师在下列案件中担任 {{criminal_role|辩护人/诉讼代理人}}：",
            indent=True)
        add_para(doc, "（一）犯罪嫌疑人/被告人或被代理人：{{criminal_subject_name}}", indent=True)
        add_para(doc, "（二）涉嫌罪名或案件事项：{{case_cause}}　　（三）委托阶段：{{criminal_stages}}", indent=True)
    else:
        add_para(doc,
            "乙方接受甲方委托，指派 {{lawyer_name}} 律师及其团队担任甲方代理：",
            indent=True)
        add_para(doc, "（一）案由：{{case_cause}}　　（二）对方当事人：{{opponent_name}}",
                 indent=True)
        add_para(doc, "（三）管辖法院：{{case_court}}　　（四）代理阶段：{{litigation_stage}}",
                 indent=True)
        add_para(doc, "（五）争议标的额：人民币 {{disputed_amount}} 元",
                 indent=True)

    # 第二条
    add_h1(doc, "第二条 代理权限")
    add_para(doc,
        "乙方的具体代理权限以双方签订的《授权委托书》载明为准。"
        "特别授权（含和解、撤诉、反诉等）须在《授权委托书》中逐项列明。",
        indent=True)

    # 第三条
    add_h1(doc, "第三条 乙方义务")
    add_para(doc,
        "（一）恪守律师职业道德与执业纪律，勤勉尽责完成委托事务；"
        "（二）按法律规定的时限及时提交证据、参加庭审；"
        "（三）对代理过程中知悉的甲方商业秘密、个人隐私及其他不愿公开信息依法负有保密义务；"
        "（四）及时通报案件进展，但不就案件最终结果作出任何承诺或保证。",
        indent=True)

    # 第四条
    add_h1(doc, "第四条 甲方义务")
    add_para(doc,
        "（一）如实陈述案情，提供真实、完整、合法的证据材料；"
        "（二）积极协助乙方工作，依约支付律师费及办案费用；"
        "（三）承担变更联系方式的告知义务；"
        "（四）不得要求乙方从事违法违规、有悖律师执业规范的活动。",
        indent=True)

    # 第五条
    add_h1(doc, "第五条 律师费")
    if kind == "风险代理":
        add_para(doc,
            "（一）双方已经单独核对本委托事项是否属于现行规定允许实行风险代理的范围；"
            "未经人工确认，不得签署或使用本风险代理合同。",
            indent=True)
        add_para(doc,
            "（二）双方协商并经人工核验的计费基数、比例或者金额、分段方式、实现条件、"
            "支付时点和最高收费限制如下：{{risk_fee_terms}}",
            indent=True)
        add_para(doc,
            "（三）诉讼费、保全费、保全担保费、鉴定费、公证费、评估费及经双方确认的"
            "差旅等第三方费用或者工作费用，按以下约定承担：{{case_expense_terms}}",
            indent=True)
    elif kind == "执行":
        add_para(doc,
            "（一）基础代理费：人民币 {{fee_amount_cn}}（¥ {{fee_amount}}）；"
            "（二）支付安排：{{fee_payment_terms}}",
            indent=True)
        add_para(doc,
            "（三）如双方拟采用风险代理，须在确认事项不属于禁止风险代理范围后，"
            "另行签订专门书面风险代理合同，明确风险责任、收费方式、分段上限和风险提示；"
            "（四）本合同不预设风险代理比例；"
            "（五）第三方费用和工作费用承担：{{case_expense_terms}}",
            indent=True)
    else:
        add_para(doc,
            "（一）律师费合计：人民币 {{fee_amount_cn}}（¥ {{fee_amount}}）；",
            indent=True)
        add_para(doc, "（二）支付安排：{{fee_payment_terms}}",
                 indent=True)
        add_para(doc,
                 "（三）诉讼费、保全费、保全担保费、鉴定费、公证费、评估费及经双方确认的"
                 "差旅等第三方费用或者工作费用，按以下约定承担：{{case_expense_terms}}",
                 indent=True)

    # 第六条
    add_h1(doc, "第六条 特别约定")
    if kind == "刑事":
        add_para(doc,
            "（一）律师费按诉讼阶段分别计付：侦查阶段 {{fee_amount}} 元；"
            "审查起诉阶段 {{fee_amount}} 元；一审阶段 {{fee_amount}} 元；"
            "二审阶段 {{fee_amount}} 元；申诉阶段另议。",
            indent=True)
        add_para(doc,
            "（二）每一阶段开始前甲方付清对应阶段律师费；"
            "（三）律师会见在押人员须遵守看守所规定，不得为在押人员传递信件、物品、帮助串供翻供。",
            indent=True)
    elif kind == "行政":
        add_para(doc,
            "（一）行政诉讼起诉/复议期限为法定除斥期间，逾期可能丧失诉权；"
            "（二）行政诉讼中被告对行政行为承担举证责任；"
            "（三）涉及国家赔偿请求的，乙方协助甲方明确赔偿义务机关及金额范围。",
            indent=True)
    else:
        add_para(doc,
            "（一）乙方律师不就案件最终结果向甲方作任何承诺；"
            "（二）案件以判决、裁定、调解、和解或撤诉方式结案时，按约定代理阶段和实际履行情况结算；"
            "（三）合同解除后的费用，按已完成工作、约定阶段和可归责事由据实结算，未发生部分依约处理。",
            indent=True)

    # 第七条
    add_h1(doc, "第七条 合同变更与解除")
    add_para(doc,
        "（一）经双方协商一致可变更或解除本合同；"
        "（二）甲方逾期 15 日不支付律师费的，乙方有权解除合同；"
        "（三）乙方工作存在严重失职或违反执业规范的，甲方有权解除合同；"
        "（四）合同解除后的费用按已完成工作、约定阶段和可归责事由据实结算。",
        indent=True)

    # 第八条
    add_h1(doc, "第八条 争议解决")
    add_para(doc,
        "因履行本合同发生的争议，提交乙方住所地有管辖权的人民法院通过诉讼解决。",
        indent=True)

    # 签字
    add_para(doc, "")
    add_para(doc, "")
    add_para(doc,
        "甲方（签字/盖章）：__________________    乙方（盖章）：{{firm_name}}",
        indent=False, align=WD_ALIGN_PARAGRAPH.LEFT)
    add_para(doc,
        "代表人（签字）：__________________    代表（签字）：__________________",
        indent=False)
    add_para(doc,
        "签约日期：_______ 年 _______ 月 _______ 日    签约地点：_____________",
        indent=False)

    save(doc, out_path)
    print(f"  ✓ {Path(out_path).name}")


# ============================================================
# 4) 法律顾问合同
# ============================================================

def make_legal_advisor():
    out_path = SKILL_DIR / "references/04-法律顾问合同/法律顾问合同（常年）.docx"
    doc = make_base_doc()
    add_title(doc, "常 年 法 律 顾 问 服 务 合 同")

    add_para(doc, "甲方（聘请方）：{{client_name}}", indent=False)
    add_para(doc, "统一社会信用代码：{{client_id}}", indent=False)
    add_para(doc, "地址：{{client_address}}    电话：{{client_phone}}", indent=False)
    add_para(doc, "")
    add_para(doc, "乙方（受聘方）：{{firm_name}}", indent=False)
    add_para(doc, "地址：{{firm_address}}    电话：{{firm_phone}}", indent=False)
    add_para(doc, "")

    add_para(doc,
        "甲方聘请乙方担任常年法律顾问，经协商达成如下协议。",
        indent=True)

    add_h1(doc, "第一条 服务范围")
    add_para(doc,
        "（一）法律咨询：就甲方日常经营管理活动提供电话/邮件/当面咨询；"
        "（二）合同审查：起草、审查、修改各类合同、协议及法律文件；"
        "（三）决策支持：就重大经营决策提供法律风险分析；"
        "（四）法律培训：根据甲方安排为员工提供法律知识培训；"
        "（五）争议解决：代理参加诉讼/仲裁/调解（需另行委托并支付代理费）。",
        indent=True)

    add_h1(doc, "第二条 服务期限")
    add_para(doc,
        "本合同期限自 {{service_start_date}} 起至 {{service_end_date}} 止。"
        "期满前三十日双方可协商续签。",
        indent=True)

    add_h1(doc, "第三条 服务方式")
    add_para(doc,
        "（一）电话/邮件咨询：工作时间随时响应；"
        "（二）现场服务：每月不少于 {{onsite_count}} 次，每次不少于 {{onsite_hours}} 小时；"
        "（三）紧急事项：可随时联系乙方律师响应。",
        indent=True)

    add_h1(doc, "第四条 顾问费")
    add_para(doc,
        "（一）年度法律顾问费：人民币 {{annual_fee_cn}}（¥ {{annual_fee}}）；"
        "（二）支付方式：□ 年付   □ 半年付   □ 季付；"
        "（三）顾问费不包括：1）诉讼/仲裁代理费；2）专项非诉法律事务费用；"
        "3）重大复杂项目费用。甲方委托诉讼等事项的，须另行签订委托代理合同。",
        indent=True)

    add_h1(doc, "第五条 双方义务")
    add_para(doc,
        "（一）乙方指派 {{lawyer_name}} 律师担任法律顾问，恪守职业道德与执业纪律，"
        "对甲方提供的信息依法负有保密义务；"
        "（二）甲方应指定专人对接乙方律师，及时、全面提供业务资料，按约支付顾问费。",
        indent=True)

    add_h1(doc, "第六条 合同变更与解除")
    add_para(doc,
        "（一）任一方提前 30 日书面通知对方，可解除本合同；"
        "（二）甲方逾期支付顾问费的，每逾期一日按日万分之五加付违约金。",
        indent=True)

    add_h1(doc, "第七条 争议解决")
    add_para(doc,
        "因履行本合同发生的争议，提交乙方住所地有管辖权的人民法院通过诉讼解决。",
        indent=True)

    add_para(doc, "")
    add_para(doc, "")
    add_para(doc,
        "甲方（盖章）：__________________    乙方（盖章）：{{firm_name}}",
        indent=False)
    add_para(doc, "签约日期：_______ 年 _______ 月 _______ 日", indent=False)

    save(doc, out_path)
    print(f"  ✓ 法律顾问合同（常年）")


# ============================================================
# 5) 审批表
# ============================================================

def make_approval_tables():
    """4 个审批表"""
    paths = [
        ("收 案 审 批 表", [
            ("案  由：", "{{case_cause}}"),
            ("对方当事人：", "{{opponent_name}}"),
            ("争议标的额：", "人民币 {{disputed_amount}} 元"),
            ("承办律师：", "{{lawyer_name}}"),
            ("律师费：", "人民币 {{fee_amount}} 元"),
            ("利益冲突查询：", "□ 无冲突   □ 有冲突（详见附件）"),
            ("承办律师意见：", "签名/日期："),
            ("风控部门意见：", ""),
            ("财务部门意见：", ""),
            ("审批人意见：", "签名/日期："),
        ], "审批表-收案.docx"),

        ("刑 事 案 件 收 案 审 批 表", [
            ("涉嫌罪名或事项：", "{{case_cause}}"),
            ("犯罪嫌疑人/被告人：", "{{criminal_subject_name}}"),
            ("委托人：", "{{client_name}}"),
            ("承办律师：", "{{lawyer_name}}"),
            ("律师费：", "人民币 {{fee_amount}} 元"),
            ("利益冲突查询：", "□ 无冲突   □ 有冲突（详见附件）"),
            ("委托人与被辩护人关系：", "{{principal_relationship}}"),
            ("承办律师意见：", "签名/日期："),
            ("风控部门意见：", ""),
            ("审批人意见：", "签名/日期："),
        ], "审批表-收案（刑事）.docx"),

        ("用 章 审 批 表", [
            ("申请日期：", "{{apply_date}}"),
            ("承办律师：", "{{lawyer_name}}"),
            ("案  由：", "{{case_cause}}"),
            ("案  号：", "{{case_number}}"),
            ("用章事由：", ""),
            ("文件名称及份数：", ""),
            ("用章类型：", "□ 公章   □ 合同章   □ 财务章"),
            ("申请人签字：", ""),
            ("审批人意见：", "签名/日期："),
        ], "审批表-用章.docx"),

        ("结 案 审 批 表", [
            ("案  由：", "{{case_cause}}"),
            ("案  号：", "{{case_number}}"),
            ("承办律师：", "{{lawyer_name}}"),
            ("收案日期：", "{{accept_date}}"),
            ("结案日期：", "{{close_date}}"),
            ("结案方式：", "□ 判决  □ 调解  □ 撤诉  □ 其他"),
            ("结果摘要：", ""),
            ("收费结算：", "□ 已结清  □ 未结清（¥ {{outstanding_amount}}）"),
            ("卷宗归档：", "□ 已归档  编号：____   □ 未归档"),
            ("承办律师结案小结：", ""),
            ("审批人意见：", "签名/日期："),
        ], "审批表-结案.docx"),
    ]

    out_dir = SKILL_DIR / "references/05-审批表"
    out_dir.mkdir(parents=True, exist_ok=True)
    for title, rows, filename in paths:
        doc = make_base_doc()
        add_table(doc, title, rows)
        add_para(doc, "")
        add_para(doc,
            "说明：本表由承办律师填写并提交审批，"
            "逐级审批完成后归档至卷宗。",
            indent=False)
        save(doc, out_dir / filename)
        print(f"  ✓ {filename}")

    # 三合一（汇总三个简表）
    doc = make_base_doc()
    add_title(doc, "审 批 表 三 合 一")

    add_para(doc,
        "本汇总表用于收案/用章/结案审批并列展示，"
        "详细字段请参见对应独立审批表。",
        indent=True)

    add_table(doc, "一、收案审批（简表）", [
        ("案  由：", "{{case_cause}}"),
        ("承办律师：", "{{lawyer_name}}"),
        ("律师费：", "¥ {{fee_amount}}"),
    ])
    add_para(doc, "", indent=False)

    add_table(doc, "二、用章审批（简表）", [
        ("案  号：", "{{case_number}}"),
        ("文件或事由：", ""),
        ("用章类型：", "□ 公章   □ 合同章"),
    ])
    add_para(doc, "", indent=False)

    add_table(doc, "三、结案审批（简表）", [
        ("结案方式：", "□ 判决  □ 调解  □ 撤诉"),
        ("结案日期：", "{{close_date}}"),
        ("费用结清：", "□ 是   □ 否（¥ {{outstanding_amount}}）"),
    ])

    save(doc, out_dir / "审批表-三合一.docx")
    print("  ✓ 审批表-三合一")


# ============================================================
# 6) 加强版（统一模板）
# ============================================================

def make_form(out_path, title, fields=None, body=None):
    """通用申请书/合同生成"""
    doc = make_base_doc()
    add_title(doc, title)

    if fields:
        for label, placeholder in fields:
            add_para(doc, f"{label}：{placeholder}", indent=False)

    if body:
        for text, opts in body:
            add_para(doc, text, **(opts or {}))

    add_para(doc, "")
    add_para(doc, "")
    add_para(doc,
        "{{client_name}}（签字/盖章）：__________________    日期：_______ 年 _______ 月 _______ 日",
        indent=False)
    save(doc, out_path)
    print(f"  ✓ {Path(out_path).name}")


def make_internal_forms():
    """加强版 01-律所内部管理"""
    out_dir = SKILL_DIR / "references/加强版/01-律所内部管理"
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = [
        ("收案批办表", "案 件 受 理 审 批 单", [
            ("案  由", "{{case_cause}}"),
            ("对方当事人", "{{opponent_name}}"),
            ("承办律师", "{{lawyer_name}}"),
            ("律师费", "¥ {{fee_amount}}"),
            ("争议标的", "¥ {{disputed_amount}}"),
        ]),
        ("招投标案件登记表", "招 投 标 案 件 登 记 表", [
            ("项目名称", "{{project_name}}"),
            ("委托方", "{{client_name}}"),
            ("承办律师", "{{lawyer_name}}"),
            ("开标时间", "{{bidding_date}}"),
        ]),
        ("案件转移申请表（单个）", "单 件 案 件 转 移 申 请 表", [
            ("原承办律师", "{{lawyer_name}}"),
            ("转出所", "{{firm_name}}"),
            ("转入所", "{{target_firm}}"),
            ("案件", "{{case_cause}}"),
        ]),
        ("案件转移申请表（批量）", "批量案件转移申请表", [
            ("转出所", "{{firm_name}}"),
            ("转入所", "{{target_firm}}"),
            ("批量案件数", "{{batch_count}}"),
        ]),
        ("利益冲突豁免函", "利 益 冲 突 豁 免 函", [
            ("案件", "{{case_cause}}"),
            ("当事人", "{{client_name}}"),
        ]),
        ("律师会见在押人员专用介绍信", "律 师 会 见 在 押 人 员 介 绍 信", [
            ("案件", "{{case_cause}}"),
            ("在押人员", "{{detainee_name}}"),
            ("羁押场所", "{{detention_place}}"),
        ]),
    ]
    for filename, title, fields in spec:
        make_form(out_dir / f"{filename}.docx", title, fields=fields)


def make_application_forms():
    """加强版 03-当事人端申请书"""
    out_dir = SKILL_DIR / "references/加强版/03-当事人端申请书"
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = [
        ("人身安全保护令申请书", "人 身 安 全 保 护 令 申 请 书", None, [
            ("申请人：{{client_name}}，{{client_identity_description}}", {}),
            ("被申请人：{{opponent_name}}，{{opponent_identity_description}}", {}),
            ("", {'indent': False}),
            ("申请事项：", {'indent': False}),
            ("1）禁止被申请人对申请人实施家庭暴力；", {'indent': True}),
            ("2）禁止被申请人骚扰、跟踪、接触申请人及其相关近亲属；", {'indent': True}),
            ("3）{{additional_protective_measures}}", {'indent': True}),
            ("", {'indent': False}),
            ("事实与理由：{{domestic_violence_facts}}", {'indent': True}),
            ("证据清单：{{protection_evidence}}", {'indent': True}),
        ]),
        ("变更诉讼请求申请书", "变 更 诉 讼 请 求 申 请 书", None, [
            ("申请人：{{client_name}}", {}),
            ("案由：{{case_cause}}", {}),
            ("案号：{{case_number}}", {}),
            ("", {'indent': False}),
            ("原诉讼请求：{{original_claims}}", {'indent': True}),
            ("变更后的诉讼请求：{{new_claims}}", {'indent': True}),
            ("事实与理由：{{change_reason}}", {'indent': True}),
        ]),
        ("强制执行申请书", "强 制 执 行 申 请 书", None, [
            ("申请执行人：{{client_name}}", {}),
            ("委托诉讼代理人：{{lawyer_name}} 律师，{{firm_name}}，执业证号：{{lawyer_license}}", {}),
            ("被执行人：{{opponent_name}}", {}),
            ("", {'indent': False}),
            ("执行依据：{{execution_basis}}", {}),
            ("执行依据作出机构：{{judgment_court}}", {}),
            ("案由：{{case_cause}}", {}),
            ("文书号：{{case_number}}", {}),
            ("生效日期：{{judgment_effective_date}}", {}),
            ("执行依据判项主文：{{judgment_main_text}}", {}),
            ("", {'indent': False}),
            ("申请执行事项：{{execution_claims}}", {'indent': True}),
            ("是否有诉前/诉讼保全：{{preservation_status}}", {'indent': True}),
            ("其他财产线索：{{property_clues}}", {'indent': True}),
        ]),
        ("撤诉申请书", "撤 诉 申 请 书", None, [
            ("申请人：{{client_name}}", {}),
            ("案由：{{case_cause}}", {}),
            ("案号：{{case_number}}", {}),
            ("", {'indent': False}),
            ("申请人于 {{filing_date}} 向贵院提起本案诉讼，现因 {{withdraw_reason}}，"
             "依据《中华人民共和国民事诉讼法》第一百四十八条，自愿申请撤回起诉，请予批准。",
             {'indent': True}),
            ("已预交的诉讼费用，请求按法律规定予以退还（{{fee_refund_request}}）。",
             {'indent': True}),
        ]),
        ("解除保全申请书", "解 除 财 产 保 全 申 请 书", None, [
            ("申请人（被保全人）：{{client_name}}", {}),
            ("被申请人（保全申请人）：{{opponent_name}}", {}),
            ("案号：{{case_number}}（原保全裁定案号：{{preservation_ruling_number}}）", {}),
            ("", {'indent': False}),
            ("申请事项：请求解除对申请人名下财产的保全措施（解除范围：{{release_scope}}）。",
             {'indent': True}),
            ("事实与理由：{{release_reason}}", {'indent': True}),
        ]),
        ("网络查控申请书", "网 络 查 控 申 请 书", None, [
            ("申请执行人：{{client_name}}", {}),
            ("被执行人：{{opponent_name}}", {}),
            ("案由：{{case_cause}}", {}),
            ("文书号：{{case_number}}", {}),
            ("执行依据：{{execution_basis}}", {}),
            ("", {'indent': False}),
            ("申请事项：请求人民法院对被执行人的下列财产进行网络查控：", {'indent': False}),
            ("1）银行存款：{{bank_accounts}}；", {'indent': True}),
            ("2）不动产：{{real_estate_clues}}；", {'indent': True}),
            ("3）车辆：{{vehicle_clues}}；", {'indent': True}),
            ("4）证券、网络资金等其他财产：{{other_assets_clues}}。", {'indent': True}),
            ("事实与理由：{{execution_necessity}}", {'indent': True}),
        ]),
    ]
    for filename, title, fields, body in spec:
        make_form(out_dir / f"{filename}.docx", title, fields=fields, body=body)


def make_property_preservation_application(out_path):
    """按现行法院申请事项重建财产保全申请书。"""
    doc = make_base_doc()
    add_title(doc, "财 产 保 全 申 请 书")
    add_para(doc, "申请人：{{client_name}}，{{client_identity_description}}", indent=False)
    add_para(doc, "住所地/住址：{{client_address}}", indent=False)
    add_para(doc, "联系电话：{{client_phone}}", indent=False)
    add_para(doc, "被申请人：{{opponent_name}}，{{opponent_identity_description}}", indent=False)
    add_para(doc, "住所地/住址：{{opponent_address}}", indent=False)
    add_para(doc, "联系电话：{{opponent_phone}}", indent=False)
    add_h1(doc, "申请事项")
    add_para(doc, "{{preservation_request}}", indent=True)
    add_para(
        doc,
        "申请保全的财产价值以人民币 {{preservation_amount}} 元为限。",
        indent=True,
    )
    add_h1(doc, "事实与理由")
    add_para(doc, "{{preservation_necessity}}", indent=True)
    add_h1(doc, "财产信息或者财产线索")
    add_para(doc, "{{property_clues}}", indent=True)
    add_h1(doc, "担保情况")
    add_para(doc, "{{security_method}}", indent=True)
    add_h1(doc, "附件")
    add_para(doc, "{{attachments}}", indent=False)
    add_para(doc, "此致", indent=False)
    add_para(doc, "{{case_court}}", indent=False)
    add_para(doc, "申请人（签名/盖章）：{{client_name}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "{{sign_date}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    # 申请书的身份、线索、担保和附件字段较多；统一固定 25pt 行距（法院参考排版），压缩段间距避免落款挤到续页。
    for paragraph in doc.paragraphs:
        paragraph.paragraph_format.line_spacing = LINE_SPACING
        paragraph.paragraph_format.line_spacing_rule = LINE_SPACING_RULE
        paragraph.paragraph_format.space_after = Pt(0)
    save(doc, out_path)
    print(f"  ✓ {Path(out_path).name}")


def make_cert_forms():
    """加强版 04-身份证明"""
    out_dir = SKILL_DIR / "references/加强版/04-身份证明"
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = [
        ("法定代表人身份证明书", "法 定 代 表 人 身 份 证 明 书", None, [
            ("兹证明：{{client_name}} 公司", {}),
            ("法定代表人：{{client_legal_rep}}    身份证号：{{client_legal_rep_id}}", {}),
            ("职务：{{client_legal_rep_title}}", {}),
            ("", {'indent': False}),
            ("特此证明。", {'indent': True}),
        ]),
        ("公司员工身份证明书", "公 司 员 工 身 份 证 明 书", None, [
            ("兹有我单位员工 {{employee_name}}（身份证号 {{employee_id}}），"
             "现任 {{employee_title}} 职务。", {'indent': True}),
            ("指派其前往贵处办理 {{case_cause}} 事宜，请予接洽。",
             {'indent': True}),
        ]),
    ]
    for filename, title, fields, body in spec:
        make_form(out_dir / f"{filename}.docx", title, fields=fields, body=body)


def make_legal_representative_certificate(out_path):
    """法定代表人身份证明书正式版。"""
    doc = make_base_doc()
    add_title(doc, "法 定 代 表 人 身 份 证 明 书")
    add_para(
        doc,
        "{{client_legal_rep}}，身份证号 {{client_legal_rep_id}}，"
        "现任我单位 {{client_legal_rep_title}} 职务，为我单位法定代表人。",
        indent=True,
    )
    add_para(doc, "")
    add_para(doc, "特此证明。", indent=True)
    add_para(doc, "")
    add_para(doc, "单位名称：{{client_name}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "统一社会信用代码：{{client_credit_code}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "住所地：{{client_address}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "单位盖章：", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "{{sign_date}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    save(doc, out_path)
    print(f"  ✓ {Path(out_path).name}")


def make_employee_certificate(out_path):
    """用于证明受委托人系本单位工作人员，不替代授权委托书。"""
    doc = make_base_doc()
    add_title(doc, "工 作 人 员 身 份 证 明 书")
    add_para(
        doc,
        "{{employee_name}}，身份证号 {{employee_id}}，系我单位工作人员，"
        "现任 {{employee_title}} 职务。",
        indent=True,
    )
    add_para(
        doc,
        "本证明仅用于其在我单位与 {{opponent_name}} 因 {{case_cause}} 一案中"
        "证明工作人员身份；具体代理事项和权限以另行出具的授权委托书为准。",
        indent=True,
    )
    add_para(doc, "")
    add_para(doc, "单位名称：{{client_name}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "统一社会信用代码：{{client_credit_code}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "单位盖章：", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_para(doc, "{{sign_date}}", indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)
    save(doc, out_path)
    print(f"  ✓ {Path(out_path).name}")


def make_agreement_forms():
    """加强版 02-委托代理合同类"""
    out_dir = SKILL_DIR / "references/加强版/02-委托代理合同类"
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = [
        ("补充协议模板", "委 托 代 理 合 同 补 充 协 议", None, [
            ("鉴于 {{client_name}} 与 {{firm_name}} 已签订《委托代理合同》（编号：{{original_contract_no}}），"
             "现就新增事项达成补充协议如下：", {'indent': True}),
            ("1. 增加/变更事项：", {'indent': False}),
            ("2. 律师费调整：", {'indent': False}),
            ("3. 其他事项：", {'indent': False}),
        ]),
        ("解除协议", "委 托 代 理 合 同 解 除 协 议", None, [
            ("甲方 {{client_name}} 与乙方 {{firm_name}} 协商一致，"
             "决定解除双方签订的《委托代理合同》（编号：{{case_number}}）。",
             {'indent': True}),
            ("1. 已发生的律师费 {{fee_amount}} 元不予退还；",
             {'indent': False}),
            ("2. 已支付但未发生的律师费由乙方退还：¥ {{refund_amount}}；",
             {'indent': False}),
            ("3. 双方就本案再无任何权利义务关系。",
             {'indent': False}),
        ]),
        ("四方协议-未结案件转出", "四 方 协 议（案 件 转 出）", None, [
            ("甲方 {{firm_name}}（转出方）", {'indent': False}),
            ("乙方 {{target_firm}}（接收方）", {'indent': False}),
            ("丙方 {{client_name}}（委托人）", {'indent': False}),
            ("丁方 {{lawyer_name}}（原承办律师）", {'indent': False}),
            ("", {'indent': False}),
            ("就 {{case_cause}} 案件转所办理达成协议：", {'indent': True}),
            ("1. 承办律师变更为乙方律师；", {'indent': False}),
            ("2. 已收律师费 {{fee_amount}} 元按约定分配；", {'indent': False}),
            ("3. 丙方知悉并同意上述转所安排。", {'indent': False}),
        ]),
        ("四方协议-未结案件转入", "四 方 协 议（案 件 转 入）", None, [
            ("甲方 {{target_firm}}（接收方）", {'indent': False}),
            ("乙方 {{firm_name}}（转出方）", {'indent': False}),
            ("丙方 {{client_name}}（委托人）", {'indent': False}),
            ("丁方 {{lawyer_name}}（原承办律师）", {'indent': False}),
            ("", {'indent': False}),
            ("就 {{case_cause}} 案件承办工作转入甲方办理，协议如下：",
             {'indent': True}),
            ("1. 承办工作由甲方办理；", {'indent': False}),
            ("2. 原合同律师费分配由乙、甲方协商处理；", {'indent': False}),
            ("3. 委托人继续委托甲方办理本案。", {'indent': False}),
        ]),
        ("法律咨询服务协议（口头咨询）", "法 律 咨 询 服 务 协 议", None, [
            ("甲方 {{client_name}} 因 {{case_cause}} 事宜委托乙方提供口头法律咨询。",
             {'indent': True}),
            ("（一）服务内容：电话/当面咨询，不含书面意见书；",
             {'indent': False}),
            ("（二）服务时间：{{service_date}}；", {'indent': False}),
            ("（三）律师费：人民币 {{fee_amount_cn}}（¥ {{fee_amount}}），签订后三日内支付；",
             {'indent': False}),
            ("（四）口头咨询意见仅供甲方决策参考，不构成正式法律意见。",
             {'indent': False}),
        ]),
        ("解除合同声明", "解 除 合 合 同 声 明", None, [
            ("致 {{client_name}}：", {'indent': False}),
            ("", {'indent': False}),
            ("由于 {{terminate_reason}}，本所决定解除与您签订的《委托代理合同》"
             "（编号：{{case_number}}）。", {'indent': True}),
            ("1. 已收取的律师费 {{fee_amount}} 元不予退还；",
             {'indent': False}),
            ("2. 未收取的律师费不再收取；", {'indent': False}),
            ("3. 您可另行委托其他律所继续办理相关事务。", {'indent': False}),
        ]),
        ("非诉讼法律服务合同（专项）", "非 诉 讼 法 律 服 务 合 同", None, [
            ("甲方 {{client_name}} 因 {{case_cause}} 项目需要，委托乙方提供专项法律服务。",
             {'indent': True}),
            ("（一）服务范围：1）法律尽职调查；2）合同审查；3）参与谈判；"
             "4）出具法律意见书；5）协助办理相关审批手续。", {'indent': False}),
            ("（二）律师费：人民币 {{fee_amount_cn}}（¥ {{fee_amount}}），"
             "签订后五日内一次性支付。", {'indent': False}),
            ("（三）如工作量显著增加，双方协商增补费用。", {'indent': False}),
        ]),
    ]
    for filename, title, fields, body in spec:
        make_form(out_dir / f"{filename}.docx", title, fields=fields, body=body)


def make_agreement_protocol():
    """加强版 05-协议模板"""
    out_path = SKILL_DIR / "references/加强版/05-协议模板/债权转让协议（无偿）.docx"
    make_form(out_path, "债 权 转 让 协 议（无 偿）", fields=[
        ("甲方（转让人）", "{{client_name}}"),
        ("乙方（受让人）", "{{opponent_name}}"),
    ], body=[
        ("一、债权基本情况：甲方对债务人享有 {{case_cause}} 债权，"
         "金额为人民币 {{disputed_amount}} 元，详见附件。", {'indent': True}),
        ("", {'indent': False}),
        ("二、转让方式：甲方将该债权无偿转让给乙方，自协议签订之日起，"
         "与债权有关的全部权利（包括但不限于诉讼/仲裁权利）一并转移。",
         {'indent': True}),
        ("", {'indent': False}),
        ("三、通知义务：甲方应在协议签订后及时通知债务人；由乙方主张债权时自行通知。",
         {'indent': True}),
    ])


# ============================================================
# 主入口
# ============================================================

def main():
    print("\n=== 01-所函（民事/刑事） ===")
    make_suohan(SKILL_DIR / "references/01-所函/所函（民事）.docx", "民事")
    make_suohan(SKILL_DIR / "references/01-所函/所函（刑事）.docx", "刑事")

    print("\n=== 02-授权委托书 ===")
    # 民事-特别授权（律师版，保留全部特别授权枚举项，不删减）
    special_items = [
        "代为承认、放弃、变更诉讼请求或反诉请求；",
        "代为进行和解、调解，签署和解协议或调解书；",
        "代为提起上诉或反诉；",
        "代为承认对方当事人提出的事实主张；",
        "代为签收法律文书（含判决书、裁定书、调解书、传票等）；",
        "代为申请执行、放弃或变更执行请求；",
        "代为处理与本案相关的款项（收取或支付），含执行回款；",
        "代为处理与本案相关的其他需特别授权的事项。",
    ]
    make_authorization_letter(
        SKILL_DIR / "references/02-授权委托书/授权委托书（民事-特别授权）.docx",
        "民事-特别授权",
        special_items=special_items,
    )
    # 民事-亲属关系（公民受托人，非律师）
    # 用于当事人需找家人作诉讼代理人的场景
    # 受委托人系当事人近亲属（民事诉讼法第六十一条）
    make_authorization_letter(
        SKILL_DIR / "references/02-授权委托书/授权委托书（民事-亲属关系）.docx",
        "民事·亲属代理",
        special_items=special_items,
        civil_relative_mode=True,
    )
    # 法人或非法人组织委托本单位工作人员参加民事诉讼。
    make_organization_employee_authorization(
        SKILL_DIR / "references/02-授权委托书/授权委托书（民事-单位工作人员）.docx"
    )
    # 刑事
    make_authorization_letter(
        SKILL_DIR / "references/02-授权委托书/授权委托书（刑事）.docx",
        "刑事",
        criminal_stages=[
            "侦查阶段：会见、提供法律咨询、代理申诉控告、申请变更强制措施",
            "审查起诉阶段：阅卷、会见、提出辩护意见",
            "一审阶段：出庭辩护、提出辩护意见",
            "二审阶段：阅卷、会见、出庭或书面辩护",
            "申诉阶段：代为起草申诉材料并提交",
        ],
    )
    # 行政
    make_authorization_letter(
        SKILL_DIR / "references/02-授权委托书/授权委托书（行政）.docx",
        "行政",
        special_items=[
            "代为承认、放弃、变更诉讼请求；",
            "代为进行和解；",
            "代为提起上诉；",
            "代为申请国家赔偿；",
            "代为签收法律文书。",
        ],
    )

    print("\n=== 03-委托代理合同（5 份精简版） ===")
    for kind, filename in [
        ("民事", "委托代理合同（民事-一般代理）.docx"),
        ("风险代理", "委托代理合同（民事-风险代理）.docx"),
        ("刑事", "委托代理合同（刑事）.docx"),
        ("行政", "委托代理合同（行政）.docx"),
        ("执行", "委托代理合同（执行）.docx"),
    ]:
        make_contract(SKILL_DIR / "references/03-委托代理合同" / filename, kind)

    print("\n=== 04-法律顾问合同 ===")
    make_legal_advisor()

    print("\n=== 05-审批表 ===")
    make_approval_tables()

    print("\n=== 加强版 01-律所内部管理 ===")
    make_internal_forms()

    print("\n=== 加强版 02-委托代理合同类 ===")
    make_agreement_forms()

    print("\n=== 加强版 03-当事人端申请书 ===")
    make_application_forms()
    make_property_preservation_application(
        SKILL_DIR / "references/加强版/03-当事人端申请书/财产保全申请书.docx"
    )

    print("\n=== 加强版 04-身份证明 ===")
    make_cert_forms()
    make_legal_representative_certificate(
        SKILL_DIR / "references/加强版/04-身份证明/法定代表人身份证明书.docx"
    )
    make_employee_certificate(
        SKILL_DIR / "references/加强版/04-身份证明/公司员工身份证明书.docx"
    )

    print("\n=== 加强版 05-协议模板 ===")
    make_agreement_protocol()

    print("\n=== 完成 ===")


if __name__ == '__main__':
    main()
