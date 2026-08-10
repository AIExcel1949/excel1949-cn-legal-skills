"""CHECKPOINT 机制 + 工具函数 — v3.2 共享层
被 4 个 asr_<name>.py 与 transcribe.py dispatcher 共用。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import sys
_HERE = Path(__file__).parent
_SKILL_ROOT = _HERE.parent
sys.path.insert(0, str(_SKILL_ROOT))
from config import is_backend_ready  # noqa: E402

SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".mp4"}
MAX_DURATION_SECONDS = 4 * 3600
SUGGESTED_SPLIT_SECONDS = 3600
WHISPER_FALLBACK = ["large-v3", "turbo", "medium", "small", "base", "tiny"]

_WHISPER_CACHE_MAP: dict[str, str] = {
    "tiny": "tiny.pt",
    "base": "base.pt",
    "small": "small.pt",
    "medium": "medium.pt",
    "large-v3": "large-v3.pt",
    "turbo": "large-v3-turbo.pt",
}
"""Whisper CLI 模型名 → 实际缓存文件名映射（v3.2+）。turbo 实际缓存为 large-v3-turbo.pt。"""


# ============================================================
# 工具函数
# ============================================================

def _get_audio_duration(file_path: str) -> float | None:
    """ffprobe 取音频时长（秒），不可用返回 None。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        r = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", file_path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def _format_duration(seconds: float) -> str:
    """秒数转为可读字符串。"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h} 小时 {m} 分 {s} 秒"
    return f"{m} 分 {s} 秒"


def _file_md5(path: str) -> str:
    """计算文件 MD5，仅用于兼容旧日志。"""
    h = hashlib.md5()
    try:
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(8192), b""):
                h.update(chunk)
    except OSError:
        return "无法计算"
    return h.hexdigest()


def _file_sha256(path: str) -> str:
    """计算文件 SHA-256；失败返回“无法计算”。"""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return "无法计算"
    return h.hexdigest()


def _whisper_cached_models(cache_dir: Path) -> list[str]:
    if not cache_dir.exists():
        return []
    return sorted([f.stem for f in cache_dir.glob("*.pt")])


def _whisper_fallback(requested: str, cached: list[str]) -> str | None:
    if not cached:
        return None
    # 将缓存文件名 stem 映射回标准模型名（如 large-v3-turbo → turbo）
    reverse_map = {v.rsplit(".", 1)[0]: k for k, v in _WHISPER_CACHE_MAP.items()}
    normalized = [reverse_map.get(c, c) for c in cached]
    started = False
    for m in WHISPER_FALLBACK:
        if m == requested:
            started = True
            continue
        if started and m in normalized:
            return m
    for m in WHISPER_FALLBACK:
        if m in normalized:
            return m
    return normalized[0] if normalized else None


# ============================================================
# CHECKPOINT 1: PRE-FLIGHT — 输入验证
# ============================================================

def checkpoint_1_preflight(input_path: str) -> dict[str, Any]:
    """检查输入文件存在性 + 格式合法性 + 时长。"""
    result: dict[str, Any] = {"passed": True, "warnings": [], "info": {}}
    path = Path(input_path)

    if not path.exists():
        print(f"\n{'='*60}")
        print(f"❌ CHECKPOINT 1 失败：文件不存在")
        print(f"{'='*60}")
        print(f"  指定路径: {input_path}")
        print(f"  绝对路径: {path.absolute()}")
        print(f"\n  💡 一线修复：请检查文件路径。")
        cwd = Path.cwd()
        audio_files = list(cwd.glob("*.mp3")) + list(cwd.glob("*.wav")) + list(cwd.glob("*.m4a"))
        if audio_files:
            print(f"\n  当前目录下的音频文件：")
            for f in audio_files[:10]:
                print(f"    - {f.name}")
        result["passed"] = False
        return result

    result["info"]["file_path"] = str(path.absolute())
    result["info"]["file_size_mb"] = round(path.stat().st_size / (1024 * 1024), 2)
    result["info"]["sha256"] = _file_sha256(str(path))

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        print(f"\n{'='*60}")
        print(f"❌ CHECKPOINT 1 失败：不支持的音频格式")
        print(f"{'='*60}")
        print(f"  文件格式: {suffix}")
        print(f"  支持的格式: {', '.join(sorted(SUPPORTED_FORMATS))}")
        print(f"\n  💡 仍失败兜底：ffmpeg 转格式: ffmpeg -i {path.name} output.mp3")
        result["passed"] = False
        return result

    result["info"]["format"] = suffix

    duration = _get_audio_duration(str(path))
    if duration is not None:
        result["info"]["duration_seconds"] = duration
        result["info"]["duration_display"] = _format_duration(duration)
        if duration > MAX_DURATION_SECONDS:
            print(f"\n⚠️  CHECKPOINT 1 警告：录音时长超过 4 小时上限（{_format_duration(duration)}）")
            print(f"  💡 建议分段: ffmpeg -i {path.name} -f segment -segment_time 3600 out_%03d.mp3")
            result["warnings"].append("录音超过4小时上限")
        elif duration > SUGGESTED_SPLIT_SECONDS:
            print(f"\n💡 CHECKPOINT 1 提示：录音超过 1 小时（{_format_duration(duration)}）")
            result["warnings"].append("录音超过1小时，建议分段")
    else:
        print(f"\n⚠️  CHECKPOINT 1 提示：无法校验录音时长（ffprobe 不可用）")
        result["warnings"].append("【未校验录音时长】")

    if result["passed"]:
        print(f"\n✅ CHECKPOINT 1 通过 (PRE-FLIGHT)")
        print(f"  文件: {path.name}")
        print(f"  格式: {suffix}")
        print(f"  大小: {result['info']['file_size_mb']} MB")
        if result["info"].get("duration_display"):
            print(f"  时长: {result['info']['duration_display']}")
    return result


# ============================================================
# CHECKPOINT 2: BACKEND CHECK — backend 模型缓存状态
# ============================================================

def checkpoint_2_backend_check(backend_name: str, settings: dict[str, Any]) -> dict[str, Any]:
    """检查 backend 模型是否已就位。未就位时提示安装命令。"""
    result: dict[str, Any] = {"passed": True, "warnings": [], "info": {}}
    ready, msg = is_backend_ready({"backends": {backend_name: settings}}, backend_name)
    if ready:
        print(f"\n✅ CHECKPOINT 2 通过 (BACKEND CHECK)")
        print(f"  backend: {backend_name}")
        print(f"  状态: {msg}")
        result["info"]["ready"] = True
    else:
        print(f"\n{'='*60}")
        print(f"⚠️  CHECKPOINT 2 警告：backend {backend_name} 未就位")
        print(f"{'='*60}")
        print(f"  {msg}")
        print(f"\n  💡 一线修复:")
        print(f"     - 装 Python 依赖: pip install <对应包> --break-system-packages")
        print(f"     - 装模型: python3 scripts/config.py doctor  # 看如何触发下载")
        print(f"     - 或运行 bash scripts/install.sh --backend {backend_name}")
        result["passed"] = False
        result["info"]["ready"] = False
        result["info"]["message"] = msg
    return result


def checkpoint_2_whisper_model(model: str) -> dict[str, Any]:
    """Whisper 专属：检查模型缓存 + 降级建议。"""
    result: dict[str, Any] = {"passed": True, "warnings": [], "info": {}}
    cache_dir = Path.home() / ".cache" / "whisper"
    cache_filename = _WHISPER_CACHE_MAP.get(model, f"{model}.pt")
    model_file = cache_dir / cache_filename
    if model_file.exists():
        sz = round(model_file.stat().st_size / (1024 * 1024), 1)
        print(f"  Whisper 模型: {model} ({sz} MB) @ {model_file}")
        result["info"]["cached"] = True
        result["info"]["cache_path"] = str(model_file)
        return result
    print(f"\n⚠️  Whisper 模型 {model} 未缓存")
    cached = _whisper_cached_models(cache_dir)
    if cached:
        print(f"  已缓存: {', '.join(cached)}")
        fb = _whisper_fallback(model, cached)
        if fb:
            print(f"  💡 建议降级到: {fb}")
            result["info"]["fallback_model"] = fb
    result["info"]["cached"] = False
    return result


# ============================================================
# CHECKPOINT 3: POST-TRANSCRIBE — 输出验证
# ============================================================

def checkpoint_3_post_transcribe(output_dir: Path) -> dict[str, Any]:
    """验证输出文件合理 + JSON 可解析。"""
    result: dict[str, Any] = {"passed": True, "warnings": [], "info": {}}
    json_file = output_dir / "transcript.json"
    if not json_file.exists():
        print(f"\n❌ CHECKPOINT 3 失败：transcript.json 不存在 ({json_file})")
        result["passed"] = False
        return result
    size = json_file.stat().st_size
    result["info"]["json_size_kb"] = round(size / 1024, 1)
    if size < 100:
        print(f"\n❌ CHECKPOINT 3 失败：JSON 异常小 ({size} 字节)")
        result["passed"] = False
        return result
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments = data.get("segments", [])
        result["info"]["segment_count"] = len(segments)
        result["info"]["text_length"] = len(data.get("text", ""))
        if segments:
            avg = sum(s.get("avg_logprob", 0) for s in segments) / len(segments)
            result["info"]["avg_logprob"] = round(avg, 3)
        print(f"\n✅ CHECKPOINT 3 通过 (POST-TRANSCRIBE)")
        print(f"  segment 数: {len(segments)}, 文本: {result['info']['text_length']} 字符")
        if segments:
            print(f"  平均置信度: {result['info']['avg_logprob']}")
    except json.JSONDecodeError as e:
        print(f"\n❌ CHECKPOINT 3 失败：JSON 解析错误 {e}")
        result["passed"] = False
    return result
