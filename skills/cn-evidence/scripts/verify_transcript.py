#!/usr/bin/env python3
"""
转写核验脚本 — cn-evidence v3.2

对转写结果进行 5 维核验：完整性、时间戳连续性、置信度统计、
内容幻听检测、格式检查。生成结构化核验报告。

调用方式:
    python3 verify_transcript.py --transcript transcript.json --output 核验报告.md
    python3 verify_transcript.py --transcript transcript.json --audio 录音.mp3 --output 核验报告.md

依赖:
    - Python 3.10+
    - ffprobe（可选，用于音频时长对比）

===== 5 维核验 =====

1. 完整性检查：空白段检测、时长对比
2. 时间戳连续性：间隔 > 5 秒标注、重叠检测
3. 置信度统计：平均 logprob、低置信度比例、no_speech_prob 分布
4. 内容检查：幻听检测（重复短语/无意义字符）、关键信息覆盖
5. 格式检查：文字稿三段式结构、时间戳格式、校核说明

===== 失败模式表 =====

| 触发条件               | 一线修复                                  | 仍失败兜底                   |
|-----------------------|------------------------------------------|----------------------------|
| JSON 解析失败          | 检查文件是否为有效 Whisper 输出             | 标注"无法核验"               |
| segments 字段缺失      | 仅做内容级检查（幻听/关键信息）              | 标注"仅部分核验"             |
| 音频文件不可用          | 跳过时长对比，仅做结构检查                   | 标注"【未对比原始音频】"      |
| ffprobe 不可用         | 跳过精确时长对比                            | 标注"【未对比原始音频时长】"  |
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# ============================================================
# 数据加载
# ============================================================

def load_transcript_data(file_path: str) -> dict | None:
    """加载 Whisper JSON 转录数据。"""
    path = Path(file_path)
    if not path.exists():
        print(f"\n❌ 文件不存在: {file_path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"\n❌ 文件加载失败: {e}")
        return None


def get_audio_duration(file_path: str) -> float | None:
    """通过 ffprobe 获取音频时长（秒）。"""
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", file_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


# ============================================================
# 核验维度 1: 完整性检查
# ============================================================

def verify_completeness(segments: list, audio_duration: float | None) -> dict:
    """检查转写的完整性。"""
    findings = []
    details = {}

    if not segments:
        findings.append({"level": "error", "message": "无转写段落（segments 为空）"})
        return {"findings": findings, "details": details}

    # 1.1 空白段检测（相邻 segment 之间间隔 > 30 秒）
    gaps = []
    for i in range(1, len(segments)):
        prev_end = segments[i-1].get("end", 0)
        curr_start = segments[i].get("start", 0)
        gap = curr_start - prev_end
        if gap > 30:
            gaps.append({
                "start_time": _sec_to_ts(prev_end),
                "end_time": _sec_to_ts(curr_start),
                "gap_seconds": round(gap, 1),
            })

    if gaps:
        findings.append({
            "level": "warning",
            "message": f"发现 {len(gaps)} 处超过 30 秒的空白段，可能存在遗漏",
            "detail": "; ".join(f"{g['start_time']}-{g['end_time']}({g['gap_seconds']}秒)" for g in gaps),
        })
    else:
        findings.append({"level": "pass", "message": "无明显空白段（> 30 秒）"})

    details["gap_count"] = len(gaps)
    details["gaps"] = gaps

    # 1.2 转写覆盖率（对比原始音频时长）
    if audio_duration is not None and segments:
        last_end = segments[-1].get("end", 0)
        first_start = segments[0].get("start", 0)
        transcript_duration = last_end - first_start
        coverage = transcript_duration / audio_duration if audio_duration > 0 else 0
        details["audio_duration"] = audio_duration
        details["transcript_duration"] = transcript_duration
        details["coverage"] = round(coverage * 100, 1)

        if coverage < 0.5:
            findings.append({
                "level": "error",
                "message": f"转写覆盖率仅 {details['coverage']}%（< 50%），可能大量遗漏",
            })
        elif coverage < 0.8:
            findings.append({
                "level": "warning",
                "message": f"转写覆盖率 {details['coverage']}%（< 80%），少于预期",
            })
        elif coverage > 1.2:
            findings.append({
                "level": "warning",
                "message": f"转写覆盖率 {details['coverage']}%（> 120%），可能包含幻听内容",
            })
        else:
            findings.append({
                "level": "pass",
                "message": f"转写覆盖率 {details['coverage']}%——正常（80%-120%）",
            })
    elif audio_duration is None and segments:
        findings.append({"level": "info", "message": "【未对比原始音频时长】——ffprobe 不可用或未提供音频文件"})
        details["audio_duration"] = None

    # 1.3 段落数量合理性
    if len(segments) < 3 and audio_duration and audio_duration > 60:
        findings.append({
            "level": "warning",
            "message": f"长时间录音（{audio_duration:.0f}秒）仅 {len(segments)} 个段落，可能遗漏大量内容",
        })

    return {"findings": findings, "details": details}


# ============================================================
# 核验维度 2: 时间戳连续性
# ============================================================

def verify_timestamps(segments: list) -> dict:
    """检查时间戳的连续性和一致性。"""
    findings = []
    details = {"overlaps": 0, "backwards": 0, "gaps_5s": 0}

    if len(segments) < 2:
        findings.append({"level": "info", "message": "段落数少于 2，跳过时间戳连续性检查"})
        return {"findings": findings, "details": details}

    overlaps = []
    backwards = []
    gaps_5s = []

    for i in range(1, len(segments)):
        prev_end = segments[i-1].get("end", 0)
        curr_start = segments[i].get("start", 0)
        curr_end = segments[i].get("end", 0)

        # 2.1 重叠检测
        if curr_start < prev_end:
            overlaps.append({
                "index": i,
                "prev_end": _sec_to_ts(prev_end),
                "curr_start": _sec_to_ts(curr_start),
                "overlap": round(prev_end - curr_start, 2),
            })

        # 2.2 倒序检测
        if curr_start < segments[i-1].get("start", 0):
            backwards.append({"index": i})

        # 2.3 小间隔（5-30 秒）
        gap = curr_start - prev_end
        if 5 <= gap <= 30:
            gaps_5s.append({
                "index": i,
                "gap_seconds": round(gap, 1),
                "location": f"{_sec_to_ts(prev_end)}-{_sec_to_ts(curr_start)}",
            })

        # 2.4 负时长检测
        if curr_end < curr_start:
            findings.append({
                "level": "error",
                "message": f"段落 {i} 时长为负: end({curr_end}) < start({curr_start})",
            })

    details["overlaps"] = len(overlaps)
    details["backwards"] = len(backwards)
    details["gaps_5s"] = len(gaps_5s)

    if overlaps:
        findings.append({
            "level": "warning",
            "message": f"发现 {len(overlaps)} 处段落时间重叠",
            "detail": "，".join(f"第{o['index']}段({o['curr_start']} < {o['prev_end']})" for o in overlaps[:5]),
        })
    else:
        findings.append({"level": "pass", "message": "无时间戳重叠"})

    if backwards:
        findings.append({
            "level": "error",
            "message": f"发现 {len(backwards)} 处时间戳倒序",
        })
    else:
        findings.append({"level": "pass", "message": "时间戳严格递增"})

    if gaps_5s:
        findings.append({
            "level": "info",
            "message": f"发现 {len(gaps_5s)} 处 5-30 秒的小间隔（可能是自然停顿）",
        })

    return {"findings": findings, "details": details}


# ============================================================
# 核验维度 3: 置信度统计
# ============================================================

def verify_confidence(segments: list) -> dict:
    """统计置信度相关的指标。"""
    findings = []
    details = {}

    if not segments:
        return {"findings": findings, "details": details}

    logprobs = [s.get("avg_logprob", 0) for s in segments]
    no_speech_probs = [s.get("no_speech_prob", 0) for s in segments]
    compression_ratios = [s.get("compression_ratio", 1.0) for s in segments]

    avg_logprob = sum(logprobs) / len(logprobs)
    low_conf_count = sum(1 for lp in logprobs if lp < -1.0)
    low_conf_ratio = low_conf_count / len(segments)
    high_no_speech = sum(1 for nsp in no_speech_probs if nsp > 0.8)
    hallucinations = sum(1 for cr in compression_ratios if cr > 2.4)

    details["avg_logprob"] = round(avg_logprob, 3)
    details["low_confidence_count"] = low_conf_count
    details["low_confidence_ratio"] = round(low_conf_ratio * 100, 1)
    details["high_no_speech_count"] = high_no_speech
    details["hallucination_count"] = hallucinations

    if avg_logprob < -1.5:
        findings.append({
            "level": "error",
            "message": f"平均置信度极低 (avg_logprob={avg_logprob:.2f})，转写质量差",
        })
    elif avg_logprob < -0.5:
        findings.append({
            "level": "warning",
            "message": f"平均置信度偏低 (avg_logprob={avg_logprob:.2f})，建议人工重点核对",
        })
    else:
        findings.append({"level": "pass", "message": f"平均置信度正常 (avg_logprob={avg_logprob:.2f})"})

    if low_conf_ratio > 0.2:
        findings.append({
            "level": "error",
            "message": f"低置信度段落比例 {low_conf_ratio*100:.1f}%（> 20%），转写质量较差",
        })
    elif low_conf_ratio > 0.1:
        findings.append({
            "level": "warning",
            "message": f"低置信度段落比例 {low_conf_ratio*100:.1f}%（> 10%）",
        })
    else:
        findings.append({
            "level": "pass",
            "message": f"低置信度段落: {low_conf_count}/{len(segments)} ({low_conf_ratio*100:.1f}%)",
        })

    if hallucinations > 0:
        findings.append({
            "level": "warning",
            "message": f"检测到 {hallucinations} 个疑似幻听段落（compression_ratio > 2.4）",
        })
    else:
        findings.append({"level": "pass", "message": "未检测到幻听段落"})

    return {"findings": findings, "details": details}


# ============================================================
# 核验维度 4: 内容检查
# ============================================================

# 法律录音常见关键信息正则
KEY_PATTERNS = {
    "金额": re.compile(r"(\d+[万亿千百]?\s*(块|元|块钱))|(\d+\.?\d*\s*万)"),
    "日期": re.compile(r"(\d{1,2}\s*[月号日])|([一二三四五六七八九十]\s*月)|(\d{4}\s*年)"),
    "利率": re.compile(r"(LPR|利息|利率|几分|几厘|四倍)"),
    "人名电话": re.compile(r"([张王李赵陈刘杨黄吴周孙马胡朱何罗高林郑])\s*(某某|总|律师)"),
}

# 幻听检测：重复短语阈值
REPEAT_THRESHOLD = 3

# 常见幻听模式
HALLUCINATION_PATTERNS = [
    re.compile(r"(谢谢观看|订阅我的频道|请点赞关注|Thank you for watching)", re.IGNORECASE),
    re.compile(r"([。，！？]{3,})"),  # 连续标点
    re.compile(r"([一-鿿])\1{10,}"),  # 同一汉字连续 10 次以上
]


def verify_content(segments: list) -> dict:
    """检查转写内容的合理性和关键信息覆盖。"""
    findings = []
    details = {}

    if not segments:
        return {"findings": findings, "details": details}

    all_text = " ".join(s.get("text", "") for s in segments)

    # 4.1 关键信息覆盖
    coverage = {}
    for key, pattern in KEY_PATTERNS.items():
        matches = pattern.findall(all_text)
        coverage[key] = len(matches)

    details["key_info_coverage"] = coverage

    missing_keys = [k for k, v in coverage.items() if v == 0]
    if missing_keys:
        findings.append({
            "level": "info",
            "message": f"未检测到以下类型的关键信息: {', '.join(missing_keys)}（可能此录音不涉及）",
        })
    else:
        findings.append({
            "level": "pass",
            "message": f"关键信息覆盖正常: " + ", ".join(f"{k}({v}处)" for k, v in coverage.items()),
        })

    # 4.2 幻听模式检测
    hallucination_matches = []
    for pattern in HALLUCINATION_PATTERNS:
        matches = pattern.findall(all_text)
        if matches:
            hallucination_matches.extend(matches)

    if hallucination_matches:
        findings.append({
            "level": "warning",
            "message": f"检测到 {len(hallucination_matches)} 处疑似幻听模式",
        })
    else:
        findings.append({"level": "pass", "message": "未检测到明显幻听模式"})

    # 4.3 重复短语检测
    word_count = {}
    for seg in segments:
        text = seg.get("text", "").strip()
        if len(text) > 10:  # 只检查长度 > 10 字的段落
            word_count[text] = word_count.get(text, 0) + 1

    repeated = {k: v for k, v in word_count.items() if v >= REPEAT_THRESHOLD}
    details["repeated_phrases"] = len(repeated)
    if repeated:
        findings.append({
            "level": "warning",
            "message": f"发现 {len(repeated)} 个短语重复 {REPEAT_THRESHOLD} 次以上（可能为幻听循环）",
            "detail": "；".join(f'"{k[:30]}..." ({v}次)' for k, v in list(repeated.items())[:3]),
        })

    # 4.4 空段落检测
    empty_segments = [i for i, s in enumerate(segments) if not s.get("text", "").strip()]
    details["empty_segments"] = len(empty_segments)
    if empty_segments:
        findings.append({
            "level": "info",
            "message": f"发现 {len(empty_segments)} 个空段落",
        })

    return {"findings": findings, "details": details}


# ============================================================
# 核验维度 5: 格式检查（仅 Markdown 输出）
# ============================================================

def verify_format(text: str) -> dict:
    """检查 Markdown 文字稿的格式是否完整。"""
    findings = []
    details = {}

    # 5.1 v3.2 三段式结构
    sections = {
        "录音基本信息": "## 一、录音基本信息" in text,
        "文字稿正文": "## 二、文字稿正文" in text,
        "校核说明": "## 三、校核说明" in text,
    }
    details["sections"] = sections

    missing_sections = [k for k, v in sections.items() if not v]
    if missing_sections:
        findings.append({
            "level": "warning",
            "message": f"缺少以下部分: {', '.join(missing_sections)}",
        })
    else:
        findings.append({"level": "pass", "message": "三段式结构完整"})

    # 5.2 时间戳格式（[MM:SS]）
    timestamp_pattern = re.compile(r"\[\d{2,}:\d{2}\]")
    ts_matches = timestamp_pattern.findall(text)
    details["timestamp_count"] = len(ts_matches)

    if len(ts_matches) == 0:
        findings.append({"level": "warning", "message": "未检测到时间戳 [MM:SS]"})
    else:
        # 检查格式异常
        bad_formats = re.findall(r"\[\d{1}:\d{2}\]|\[\d{2,}:\d{1}\]", text)
        if bad_formats:
            findings.append({
                "level": "warning",
                "message": f"发现 {len(bad_formats)} 处时间戳格式异常: {', '.join(bad_formats[:3])}",
            })
        else:
            findings.append({
                "level": "pass",
                "message": f"时间戳格式正确（检测到 {len(ts_matches)} 处 [MM:SS]）",
            })

    # 5.3 校核说明和状态
    review_markers = ["不替代原始录音", "以原始录音为准", "校核状态"]
    found_markers = [marker for marker in review_markers if marker in text]
    details["review_note_completeness"] = f"{len(found_markers)}/{len(review_markers)}"
    if len(found_markers) < len(review_markers):
        missing = [marker for marker in review_markers if marker not in text]
        findings.append({
            "level": "warning",
            "message": f"校核说明不完整，缺少：{', '.join(missing)}",
        })

    return {"findings": findings, "details": details}


# ============================================================
# 辅助函数
# ============================================================

def _sec_to_ts(seconds: float) -> str:
    """秒数 -> [MM:SS]."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"[{m:02d}:{s:02d}]"


# ============================================================
# 报告生成
# ============================================================

def generate_report(
    results: dict,
    file_info: dict,
    output_path: str,
) -> str:
    """生成结构化核验报告。"""
    lines = []

    lines.append("# 录音转写核验报告")
    lines.append("")

    # 基本信息
    lines.append("## 一、基本信息")
    lines.append("")
    lines.append(f"- 核验时间：{file_info.get('verify_time', '')}")
    lines.append(f"- 转写文件：{file_info.get('transcript_file', '')}")
    lines.append(f"- 原始音频：{file_info.get('audio_file', '（未提供）')}")

    seg_count = file_info.get("segment_count", 0)
    lines.append(f"- 段落总数：{seg_count}")
    lines.append(f"- 文本总长：{file_info.get('text_length', 0)} 字符")
    lines.append("")

    # 核验结果总表
    lines.append("## 二、核验结果汇总")
    lines.append("")
    lines.append("| 检查项 | 结果 | 说明 |")
    lines.append("|--------|------|------|")

    for dim_name, dim_result in results.items():
        all_findings = dim_result.get("findings", [])
        errors = [f for f in all_findings if f["level"] == "error"]
        warnings = [f for f in all_findings if f["level"] == "warning"]
        passes = [f for f in all_findings if f["level"] == "pass"]

        if errors:
            status = "❌ 不通过"
            desc = errors[0]["message"][:60]
        elif warnings:
            status = "⚠️ 警告"
            desc = warnings[0]["message"][:60]
        elif passes:
            status = "✅ 通过"
            desc = passes[0]["message"][:60]
        else:
            status = "ℹ️ 信息"
            desc = all_findings[0]["message"][:60] if all_findings else ""

        lines.append(f"| {dim_name} | {status} | {desc} |")

    lines.append("")

    # 详细检查结果
    lines.append("## 三、详细核验结果")
    lines.append("")

    for dim_name, dim_result in results.items():
        lines.append(f"### {dim_name}")
        lines.append("")

        all_findings = dim_result.get("findings", [])
        for f in all_findings:
            icon = {"error": "❌", "warning": "⚠️", "pass": "✅", "info": "ℹ️"}.get(f["level"], "•")
            lines.append(f"- {icon} {f['message']}")
            if f.get("detail"):
                lines.append(f"  - 详情：{f['detail']}")
        lines.append("")

        # 关键数据
        details = dim_result.get("details", {})
        if details:
            for k, v in details.items():
                if isinstance(v, (int, float, str)) and not isinstance(v, bool):
                    lines.append(f"  - {k}: {v}")
        lines.append("")

    # 需人工核对项
    need_review = []
    for dim_name, dim_result in results.items():
        for f in dim_result.get("findings", []):
            if f["level"] in ("warning", "error"):
                need_review.append(f"- [{dim_name}] {f['message']}")

    if need_review:
        lines.append("## 四、需人工核对项")
        lines.append("")
        for i, item in enumerate(need_review, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*本核验报告由 cn-evidence v3.2 自动生成，仅供参考。*")
    lines.append(f"*最终文字稿须经执业律师逐句核对原始录音后方可使用。*")
    lines.append("")

    report = "\n".join(lines)

    # 写入文件
    try:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    except (OSError, PermissionError) as e:
        print(f"\n❌ 无法写入核验报告: {e}")
        fallback = Path.cwd() / output.name
        fallback.write_text(report, encoding="utf-8")
        print(f"  💡 兜底：降级到当前目录: {fallback}")

    return report


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="转写核验 — 对录音转写结果进行 5 维质量核验",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本核验（仅检查 JSON）
  python3 verify_transcript.py --transcript transcript.json --output 核验报告.md

  # 完整核验（含原始音频对比）
  python3 verify_transcript.py --transcript transcript.json --audio 录音.mp3 --output 核验报告.md

  # 核验 Markdown 文字稿（格式检查）
  python3 verify_transcript.py --transcript 文字稿.md --output 核验报告.md
        """,
    )

    parser.add_argument("--transcript", "-t", required=True,
                        help="转写文件路径（Whisper JSON 或 Markdown 文字稿）")
    parser.add_argument("--audio", "-a", default=None,
                        help="原始音频文件路径（可选，提供后可做时长对比）")
    parser.add_argument("--output", "-o", default="核验报告.md",
                        help="核验报告输出路径（默认: 核验报告.md）")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  cn-evidence v3.2 — 转写质量核验")
    print(f"{'='*60}")

    # 加载数据
    file_ext = Path(args.transcript).suffix.lower()
    text_content = None
    format_text = None

    if file_ext == ".json":
        data = load_transcript_data(args.transcript)
        if data is None:
            sys.exit(1)
        segments = data.get("segments", [])
        text_content = data.get("text", "")
    elif file_ext in (".md", ".txt"):
        try:
            text_content = Path(args.transcript).read_text(encoding="utf-8")
        except OSError as e:
            print(f"\n❌ 文件加载失败: {e}")
            sys.exit(1)
        data = {"segments": [], "text": text_content}
        segments = []
        format_text = text_content
        print(f"\n📄 检测到文字稿文件（非 Whisper JSON），将仅执行格式检查。")
    else:
        print(f"\n❌ 不支持的文件格式: {file_ext}（支持 .json / .md / .txt）")
        sys.exit(1)

    # 音频时长
    audio_duration = None
    if args.audio:
        audio_duration = get_audio_duration(args.audio)
        if audio_duration is not None:
            print(f"\n📻 原始音频时长: {audio_duration:.1f} 秒")
        else:
            print(f"\n⚠️  无法获取音频时长（ffprobe 不可用或文件不存在）")

    print(f"\n🔍 开始核验...")

    # 执行 5 维核验
    results = {}

    if file_ext == ".json":
        results["1-完整性"] = verify_completeness(segments, audio_duration)
        results["2-时间戳"] = verify_timestamps(segments)
        results["3-置信度"] = verify_confidence(segments)
        results["4-内容"] = verify_content(segments)
    else:
        skipped = {"findings": [{"level": "info", "message": "Markdown 模式仅执行格式检查"}], "details": {}}
        results["1-完整性"] = skipped
        results["2-时间戳"] = skipped
        results["3-置信度"] = skipped
        results["4-内容"] = skipped

    if format_text:
        results["5-格式"] = verify_format(format_text)
    else:
        results["5-格式"] = {"findings": [{"level": "info", "message": "未提供文字稿文本，跳过格式检查"}], "details": {}}

    # 生成报告
    file_info = {
        "verify_time": datetime.now().strftime("%Y 年 %m 月 %d 日 %H:%M"),
        "transcript_file": args.transcript,
        "audio_file": args.audio or "（未提供）",
        "segment_count": len(segments),
        "text_length": len(text_content) if text_content else 0,
    }

    report = generate_report(results, file_info, args.output)

    # 输出摘要
    total_errors = sum(
        1 for dim in results.values()
        for f in dim.get("findings", [])
        if f["level"] == "error"
    )
    total_warnings = sum(
        1 for dim in results.values()
        for f in dim.get("findings", [])
        if f["level"] == "warning"
    )

    print(f"\n{'='*60}")
    if total_errors > 0:
        print(f"⚠️  核验完成：{total_errors} 个错误, {total_warnings} 个警告")
    elif total_warnings > 0:
        print(f"⚠️  核验完成：{total_warnings} 个警告（建议人工核对）")
    else:
        print(f"✅ 核验完成：全部通过！")
    print(f"{'='*60}")
    print(f"  核验报告: {args.output}")
    print(f"{'='*60}\n")

    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
