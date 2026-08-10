#!/usr/bin/env python3
"""
转写格式化脚本 — cn-evidence v3.2

将标准转写 JSON 格式化为可与原始录音核对的文字索引。
输出 Markdown（供校对）+ 可选 DOCX（供律师审查后按受理法院要求使用）。

调用方式:
    python3 format_transcript.py --input transcript.json --output 文字稿.md --case-info case_info.json

依赖:
    - Python 3.10+
    - python-docx>=0.8.11（可选，仅 DOCX 输出需要）

===== CHECKPOINT 机制 =====

CHECKPOINT 1: JSON 格式可解析，包含 segments 字段
CHECKPOINT 2: case_info.json（如提供）包含必填字段
CHECKPOINT 3 (POST): Markdown 输出行数 > 0; DOCX 文件大小 > 5KB

===== 失败模式表 =====

| 触发条件                  | 一线修复                            | 仍失败兜底                         |
|--------------------------|------------------------------------|----------------------------------|
| JSON 解析失败             | 检查是否为有效的 Whisper JSON 格式   | 尝试作为纯文本逐行处理              |
| segments 字段缺失         | 尝试从 text 字段读取纯文本           | 标注"无法生成带时间戳格式"          |
| case_info.json 缺失必填   | 使用占位符填充，标注"【待补充】"      | 生成最小格式的文字稿（仅正文）       |
| python-docx 未安装        | 跳过 DOCX 生成，仅输出 Markdown      | 提示安装: pip install python-docx  |
| 输出目录不可写             | 降级到当前目录                       | 标注替代路径                       |
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_PATH = SKILL_ROOT / "assets" / "录音文字稿-模板.docx"
FONT_NAME = "Source Han Sans CN"


# ============================================================
# CHECKPOINT 1: 输入 JSON 验证
# ============================================================

def checkpoint_1_json_validation(json_path: str) -> dict:
    """
    验证 Whisper JSON 输出文件的格式和内容。

    返回: {"passed": bool, "warnings": list, "data": dict|None}
    """
    result = {"passed": True, "warnings": [], "data": None}

    path = Path(json_path)
    if not path.exists():
        print(f"\n❌ CHECKPOINT 1 失败：JSON 文件不存在")
        print(f"  路径: {json_path}")
        result["passed"] = False
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"\n❌ CHECKPOINT 1 失败：JSON 解析错误")
        print(f"  错误: {e}")
        print(f"\n  💡 一线修复：检查文件是否为有效的 Whisper JSON 格式。")
        print(f"  💡 兜底方案：尝试作为纯文本逐行处理。")
        result["passed"] = False
        return result

    # 检查 segments 字段
    segments = data.get("segments", [])
    if not segments:
        # 尝试从 text 字段读取
        text = data.get("text", "")
        if text:
            print(f"\n⚠️  CHECKPOINT 1 警告：segments 字段缺失，但有 text 字段")
            print(f"  文本长度: {len(text)} 字符")
            print(f"  将按纯文本处理（无时间戳、无说话人区分）。")
            result["data"] = {"raw_text": text}
            result["warnings"].append("segments 字段缺失，按纯文本处理")
            return result
        else:
            print(f"\n❌ CHECKPOINT 1 失败：segments 和 text 字段均缺失")
            result["passed"] = False
            return result

    result["data"] = data
    print(f"\n✅ CHECKPOINT 1 通过 (JSON VALIDATION)")
    print(f"  segment 数: {len(segments)}")
    print(f"  文本总长: {len(data.get('text', ''))} 字符")

    # 统计置信度
    low_conf = sum(1 for s in segments if s.get("avg_logprob", 0) < -1.0)
    if low_conf > 0:
        print(f"  低置信度 segment: {low_conf}/{len(segments)} ({100*low_conf/len(segments):.1f}%)")
        if low_conf / len(segments) > 0.2:
            print(f"  ⚠️  低置信度比例超过 20%，转写质量可能较差，建议人工重点核对。")
            result["warnings"].append(f"低置信度比例 {100*low_conf/len(segments):.1f}%，建议人工重点核对")

    return result


# ============================================================
# CHECKPOINT 2: 案件信息验证
# ============================================================

def checkpoint_2_case_info(case_info_path: str | None) -> dict:
    """
    验证 case_info.json 的必填字段。

    返回: {"passed": bool, "warnings": list, "data": dict}
    """
    result = {"passed": True, "warnings": [], "data": {}}

    if case_info_path is None:
        print(f"\n⚠️  CHECKPOINT 2 跳过：未提供 case-info 文件")
        print(f"  将使用最小格式输出（仅正文 + 基础声明）。")
        result["warnings"].append("未提供 case-info，输出最小格式")
        return result

    path = Path(case_info_path)
    if not path.exists():
        print(f"\n⚠️  CHECKPOINT 2 警告：case-info 文件不存在")
        print(f"  路径: {case_info_path}")
        print(f"  将使用最小格式输出。")
        result["warnings"].append(f"case-info 文件不存在: {case_info_path}")
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"\n⚠️  CHECKPOINT 2 警告：case-info JSON 解析失败: {e}")
        result["warnings"].append(f"case-info JSON 解析失败: {e}")
        return result

    result["data"] = data

    # 录音时间可能无法从文件本身验证，不得为了过校验而推测。
    missing = []
    if not data.get("speakers"):
        missing.append("speakers")

    if missing:
        print(f"\n⚠️  CHECKPOINT 2 警告：case-info 缺少必填字段: {', '.join(missing)}")
        print(f"  将使用占位符填充，标注\"【待补充】\"。")
        result["warnings"].append(f"缺少必填字段: {', '.join(missing)}")
    else:
        print(f"\n✅ CHECKPOINT 2 通过 (CASE INFO)")
        print(f"  录音时间: {data.get('recording_time', '')}")
        speaker_count = len(data.get("speakers", {}))
        print(f"  说话人数: {speaker_count}")

    return result


# ============================================================
# 格式化核心逻辑
# ============================================================

def format_transcript(
    transcript_data: dict,
    case_info: dict,
    output_md: str,
    output_docx: str | None = None,
    template_path: str | None = None,
    speaker_map: dict | None = None,
) -> str:
    """
    将转写 JSON 格式化为待人工校核的录音文字稿 Markdown。

    返回: Markdown 字符串
    """
    segments = transcript_data.get("segments", [])
    raw_text = transcript_data.get("raw_text", None)

    lines = []
    lines.append("# 录音文字稿\n")

    # ===== 第一部分：录音基本信息 =====
    lines.append("## 一、录音基本信息\n")

    ri = case_info.get("recording_time", "【待补充】")
    rl = case_info.get("recording_location", "【待补充】")
    rm = case_info.get("recording_method", "【待补充】")
    rd = case_info.get("recording_duration", "【待补充】")
    of = case_info.get("original_file", "【待补充】")
    sha256 = case_info.get("original_sha256", "【待补充】")
    legacy_md5 = case_info.get("original_md5", "")

    # 构建通话双方字符串
    speakers = case_info.get("speakers", {})
    speaker_lines = []
    for key, info in sorted(speakers.items()):
        name = info.get("name", key)
        role = info.get("role", "")
        role_str = f"（{role}）" if role else ""
        speaker_lines.append(f"{key}：{name}{role_str}")
    speakers_str = "<br>".join(speaker_lines) if speaker_lines else "【待补充】"

    lines.append("| 项目 | 内容 |")
    lines.append("|------|------|")
    lines.append(f"| 录音时间 | {ri} |")
    lines.append(f"| 录音地点 | {rl} |")
    lines.append(f"| 说话人对应 | {speakers_str} |")
    lines.append(f"| 录音方式 | {rm} |")
    lines.append(f"| 录音时长 | {rd} |")
    lines.append(f"| 原始录音文件 | {of} |")
    if sha256 != "【待补充】":
        lines.append(f"| SHA-256 | {sha256} |")
    elif legacy_md5:
        lines.append(f"| MD5（兼容旧数据） | {legacy_md5} |")
    else:
        lines.append("| SHA-256 | 【待补充】 |")
    lines.append("")

    # ===== 第二部分：文字稿正文 =====
    lines.append("## 二、文字稿正文\n")

    # 说话人说明
    if speakers:
        speaker_desc_parts = []
        for key, info in sorted(speakers.items()):
            name = info.get("name", key)
            role = info.get("role", "")
            role_str = f"（{role}）" if role else ""
            speaker_desc_parts.append(f"{key} = {name}{role_str}")
        speaker_desc = "，".join(speaker_desc_parts)
        lines.append(f"> 说明：{speaker_desc}\n")
    else:
        lines.append("> 说明：说话人标签仅为声纹聚类结果，不等于身份识别，请人工确认对应关系。\n")

    # 正文段落
    if raw_text:
        # 纯文本模式
        lines.append(raw_text)
        lines.append("")
    else:
        for seg in segments:
            start_sec = seg.get("start", 0)
            time_label = _seconds_to_timestamp(start_sec)
            text = seg.get("text", "").strip()
            if not text:
                continue

            # 证据类转写不可仅依模型阈值静默删句；保留并标记供回听。
            no_speech = seg.get("no_speech_prob", 0)

            # 置信度标记
            avg_logprob = seg.get("avg_logprob", 0)
            compression_ratio = seg.get("compression_ratio", 1.0)

            if avg_logprob < -1.0:
                text = f"{text}〔低置信度，须回听〕"
            elif avg_logprob < -0.5:
                text = f"{text}〔待回听〕"

            if compression_ratio > 2.4:
                text = f"{text}〔疑似重复或幻听，须回听〕"
            if no_speech > 0.8:
                text = f"{text}〔疑似非语音，须回听〕"

            # 说话人标注（支持 diarization speaker 字段 + speaker_map 映射）
            speaker_tag = ""
            seg_speaker = seg.get("speaker", "")
            if seg_speaker and speaker_map:
                # 使用 speaker_map 将 SPEEKER_X 映射为姓名
                mapped = speaker_map.get(seg_speaker, {})
                name = mapped.get("name", seg_speaker) if isinstance(mapped, dict) else str(mapped)
                speaker_tag = f"{name}："
            elif seg_speaker:
                speaker_tag = f"{seg_speaker}："
            elif speakers:
                # 无 diarization 数据，不标注（需人工填写）
                speaker_tag = ""

            if speaker_tag:
                lines.append(f"[{time_label}] {speaker_tag}{text}")
            else:
                lines.append(f"[{time_label}] {text}")

        lines.append("")
        duration_label = rd if rd != "【待补充】" else "待核实"
        lines.append(f"（——录音结束，总时长{duration_label}——）")
        lines.append("")

    # ===== 第三部分：校核说明 =====
    lines.append("## 三、校核说明\n")

    transcriber = case_info.get("transcriber", {})
    t_name = transcriber.get("name", "【待补充】")
    t_date = transcriber.get("date", datetime.now().astimezone().strftime("%Y 年 %m 月 %d 日"))
    review_status = case_info.get("review_status", "未完成逐句回听")
    lines.append("本稿系原始录音的辅助文字索引，不替代原始录音；如文字与原始录音不一致，以原始录音为准。听不清、低置信度或说话人存疑之处，须逐句回听确认。")
    lines.append(f"校核状态：{review_status}")
    lines.append(f"整理人：{t_name}")

    # 审核人（如有）
    reviewer = case_info.get("reviewer")
    if reviewer:
        r_name = reviewer.get("name", "")
        r_date = reviewer.get("date", "")
        lines.append(f"校核人：{r_name or '【待补充】'}")
        if r_date:
            t_date = r_date
    else:
        lines.append("校核人：【待补充】")
    lines.append(f"日期：{t_date}")
    lines.append("")

    markdown_output = "\n".join(lines)
    return markdown_output


def _seconds_to_timestamp(seconds: float) -> str:
    """将秒数转换为 [MM:SS] 格式。"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _sha256_file(path: str) -> str:
    """计算原始录音 SHA-256；只读文件，不改变原始数据。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ============================================================
# DOCX 输出（可选）
# ============================================================

def generate_docx(markdown_text: str, output_path: str, template_path: str | None = None):
    """
    将格式化后的文字稿渲染为 DOCX 文件。

    依赖: python-docx
    """
    try:
        from docx import Document
        from docx.shared import Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
    except ImportError:
        print(f"\n⚠️  跳过 DOCX 生成：python-docx 未安装")
        print(f"  安装: pip install python-docx")
        return False

    selected_template = Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH
    if selected_template.exists():
        doc = Document(selected_template)
        # 模板的正文只用于人工填写示范。自动生成时清空正文，保留页眉、页脚和样式。
        body = doc._element.body
        for child in list(body):
            if child.tag != qn("w:sectPr"):
                body.remove(child)
    else:
        doc = Document()
    try:
        from build_template import add_brand_header_and_footer
        add_brand_header_and_footer(doc)
    except (ImportError, OSError) as exc:
        print(f"\n⚠️  无法写入统一页眉页脚：{exc}")
        return False

    # 无论使用默认模板、自定义模板或空白文档，统一写入品牌作者属性。
    doc.core_properties.author = "AIOffice职场通关-excel1949"
    doc.core_properties.last_modified_by = "AIOffice职场通关-excel1949"
    doc.core_properties.title = "录音文字稿"
    doc.core_properties.subject = "中国民商事录音证据转写"
    doc.core_properties.category = "AIOffice职场通关法律Skill"
    doc.core_properties.comments = "AI辅助生成，须由执业律师逐项核验"

    # 页面设置（A4 标准）
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
    normal.font.size = Pt(11)

    # 解析 Markdown 行并添加到 DOCX
    # 简化处理：按行渲染，## 作为标题，| 开头的作为表格，其他作为正文
    lines = markdown_text.split("\n")
    table_mode = False
    table_rows = []

    for line in lines:
        line = line.strip()
        if not line:
            if table_mode and table_rows:
                _add_table_to_doc(doc, table_rows)
                table_rows = []
                table_mode = False
            continue

        if line.startswith("# 录音文字稿"):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run("录音文字稿")
            run.bold = True
            run.font.size = Pt(20)
            run.font.name = FONT_NAME
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)

        elif line.startswith("## "):
            title = line[3:].strip()
            p = doc.add_paragraph()
            run = p.add_run(title)
            run.bold = True
            run.font.size = Pt(14)
            run.font.name = FONT_NAME
            run.font.color.rgb = RGBColor(0x0F, 0x5A, 0x33)
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)

        elif line.startswith("|") and not table_mode:
            table_mode = True
            table_rows = [[cell.strip() for cell in line.split("|")[1:-1]]]

        elif line.startswith("|") and table_mode:
            if "---" not in line:
                table_rows.append([cell.strip() for cell in line.split("|")[1:-1]])

        elif line.startswith(">"):
            # 引用行（说话人说明）
            p = doc.add_paragraph()
            run = p.add_run(line[1:].strip())
            run.font.size = Pt(10.5)
            run.font.name = FONT_NAME
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
            run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

        else:
            # 正文
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.font.size = Pt(11)
            run.font.name = FONT_NAME
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
            p.paragraph_format.line_spacing = 1.35

    # 处理剩余表格
    if table_mode and table_rows:
        _add_table_to_doc(doc, table_rows)

    doc.save(output_path)
    return True


def _add_table_to_doc(doc, rows):
    """向 DOCX 文档添加表格。"""
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn

    if not rows:
        return
    table = doc.add_table(rows=len(rows), cols=len(rows[0]), style="Table Grid")
    for i, row_data in enumerate(rows):
        for j, cell_text in enumerate(row_data):
            cell = table.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            parts = cell_text.split("<br>")
            for part_index, part in enumerate(parts):
                if part_index:
                    p.add_run().add_break()
                run = p.add_run(part)
                run.font.size = Pt(10)
                run.font.name = FONT_NAME
                run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
                if i == 0:
                    run.bold = True
                    run.font.color.rgb = RGBColor(0x0F, 0x5A, 0x33)
    doc.add_paragraph()  # 表格后空行


# ============================================================
# CHECKPOINT 3: 输出验证
# ============================================================

def checkpoint_3_output(output_md_path: str, output_docx_path: str | None = None) -> dict:
    """
    验证输出文件。

    返回: {"passed": bool, "warnings": list}
    """
    result = {"passed": True, "warnings": []}

    md_path = Path(output_md_path)
    if not md_path.exists():
        print(f"\n❌ CHECKPOINT 3 失败：Markdown 文件未生成")
        result["passed"] = False
        return result

    md_size = md_path.stat().st_size
    md_lines = len(md_path.read_text(encoding="utf-8").split("\n"))

    if md_lines == 0:
        print(f"\n❌ CHECKPOINT 3 失败：Markdown 文件为空")
        result["passed"] = False
        return result

    print(f"\n✅ CHECKPOINT 3 通过 (OUTPUT)")
    print(f"  Markdown: {md_path.name} ({md_lines} 行, {md_size/1024:.1f} KB)")

    if output_docx_path:
        docx_path = Path(output_docx_path)
        if docx_path.exists():
            docx_size = docx_path.stat().st_size
            if docx_size < 5000:
                print(f"  ⚠️  DOCX 文件异常小: {docx_size} 字节（< 5KB）")
                result["warnings"].append("DOCX 文件异常小")
            else:
                print(f"  DOCX: {docx_path.name} ({docx_size/1024:.1f} KB)")

    return result


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="转写格式化 — 将转写 JSON 转换为待人工校核的录音文字稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法（仅 Markdown）
  python3 format_transcript.py --input transcript.json --output 文字稿.md

  # 完整用法（Markdown + DOCX + 案件信息）
  python3 format_transcript.py \\
    --input transcript.json \\
    --output 文字稿.md \\
    --output-docx 文字稿.docx \\
    --case-info case_info.json

  # 纯文本模式（无案件信息，最小输出）
  python3 format_transcript.py --input transcript.json --output 文字稿.md
        """,
    )

    parser.add_argument("--input", "-i", required=True,
                        help="Whisper JSON 转写结果文件")
    parser.add_argument("--output", "-o", required=True,
                        help="输出 Markdown 文件路径")
    parser.add_argument("--output-docx", "-d", default=None,
                        help="输出 DOCX 文件路径（可选，需 python-docx）")
    parser.add_argument("--case-info", "-c", default=None,
                        help="案件信息 JSON 文件（可选，不提供则使用最小格式）")
    parser.add_argument("--audio", "-a", default=None,
                        help="原始录音文件（可选；用于自动计算 SHA-256 并填写文件名）")
    parser.add_argument("--template", "-t", default=None,
                        help="自定义 DOCX 模板路径（可选）")
    parser.add_argument("--speaker-map", "-s", default=None,
                        help="说话人映射 JSON 文件（将 SPEAKER_0/SPEAKER_1 映射为姓名）")

    args = parser.parse_args()

    # 加载 speaker_map
    speaker_map = None
    if args.speaker_map:
        try:
            with open(args.speaker_map, "r", encoding="utf-8") as f:
                speaker_map = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️  speaker-map 加载失败: {e}，将使用原始标签")

    print(f"\n{'='*60}")
    print(f"  cn-evidence v3.2 — 文字稿格式化")
    print(f"{'='*60}")

    # CHECKPOINT 1
    cp1 = checkpoint_1_json_validation(args.input)
    if not cp1["passed"]:
        sys.exit(1)

    # CHECKPOINT 2
    cp2 = checkpoint_2_case_info(args.case_info)
    if args.audio:
        audio_path = Path(args.audio)
        if not audio_path.is_file():
            print(f"\n❌ 原始录音文件不存在：{audio_path}")
            sys.exit(1)
        try:
            cp2["data"]["original_file"] = audio_path.name
            cp2["data"]["original_sha256"] = _sha256_file(str(audio_path))
        except OSError as error:
            print(f"\n❌ 无法读取原始录音以计算 SHA-256：{error}")
            sys.exit(1)

    # 格式化
    markdown = format_transcript(
        transcript_data=cp1["data"],
        case_info=cp2["data"],
        output_md=args.output,
        output_docx=args.output_docx,
        template_path=args.template,
        speaker_map=speaker_map,
    )

    # 写入 Markdown
    try:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    except (OSError, PermissionError) as e:
        print(f"\n❌ 无法写入 Markdown 文件: {e}")
        fallback_path = Path.cwd() / output_path.name
        print(f"  💡 兜底：降级到当前目录: {fallback_path}")
        fallback_path.write_text(markdown, encoding="utf-8")
        args.output = str(fallback_path)

    # 生成 DOCX（可选）
    if args.output_docx:
        docx_ok = generate_docx(markdown, args.output_docx, args.template)
        if not docx_ok:
            args.output_docx = None

    # CHECKPOINT 3
    cp3 = checkpoint_3_output(args.output, args.output_docx)

    # 总结
    warnings_all = cp1.get("warnings", []) + cp2.get("warnings", []) + cp3.get("warnings", [])
    print(f"\n{'='*60}")
    print(f"✅ 格式化完成！")
    print(f"{'='*60}")
    print(f"  Markdown: {args.output}")
    if args.output_docx:
        print(f"  DOCX: {args.output_docx}")
    if warnings_all:
        print(f"\n  ⚠️  警告 ({len(warnings_all)} 项):")
        for w in warnings_all:
            print(f"    - {w}")
    print(f"\n  下一步:")
    print(f"    python3 scripts/verify_transcript.py \\")
    print(f"      --transcript {args.input} \\")
    print(f"      --output 核验报告.md")
    print(f"{'='*60}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
