#!/usr/bin/env python3
"""
asr_whisper.py — Whisper CLI 后端（cn-evidence v3.2）

OpenAI Whisper CLI 默认从本 Skill 的 .venv 调用；
说话人分离走外部 scripts/diarize.py（subprocess），不内置。

===== 反例（不要这样做）=====

反例 1: "whisper CLI 自带 speaker 区分"
    错误! Whisper 原生不支持说话人分离，必须外挂 diarize.py。
反例 2: "根据通用榜单直接承诺本案录音的准确率"
    错误! 应用本案 3—5 分钟代表性样本做人工对照评测。
反例 3: "忘了加 --language zh"
    错误! Whisper 自动语言检测对中文常误判为日语/韩语。

===== CHECKPOINT 机制 =====
CHECKPOINT 1 (PRE-FLIGHT):  输入文件 + 格式 + 时长
CHECKPOINT 2 (BACKEND CHECK): Whisper 模型缓存 + 降级建议
CHECKPOINT 3 (POST-TRANSCRIBE): 输出文件 + JSON 可解析
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# scripts/ 注入到 sys.path 用于 import _common / config
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from _common import checkpoints, output_naming  # noqa: E402
from _common.output_naming import (  # noqa: E402
    rename_whisper_outputs,
    write_transcribe_log,
)
from config import GLOBAL_CONFIG_PATH, get_backend_settings, load_global_config  # noqa: E402


_DEFAULT_WHISPER_BIN = str(_SCRIPT_DIR.parent / ".venv" / "bin" / "whisper")
"""Whisper CLI 默认路径（fallback）。实际运行时优先从 settings["binary"] 读取。"""


def _run_diarization_and_merge(
    input_path: str,
    output_dir: Path,
    method: str,
    num_speakers: int | None,
) -> None:
    """Whisper 路径专用：调外部 scripts/diarize.py 做说话人分离并合并。
    FunASR 系列 backend 已被内置分离，不必调。
    """
    diarize_script = _SCRIPT_DIR / "diarize.py"
    diarization_output = output_dir / "diarization.json"

    print(f"\n{'='*60}")
    print(f"  🔊 说话人分离: {method}")
    print(f"{'='*60}")

    cmd = [
        sys.executable, str(diarize_script),
        "--input", input_path,
        "--method", method,
        "--output", str(diarization_output),
    ]
    if num_speakers:
        cmd += ["--num-speakers", str(num_speakers)]

    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if r.stdout:
            print(r.stdout)
        if r.returncode != 0 and r.stderr:
            print(r.stderr)
    except subprocess.TimeoutExpired:
        print(f"⚠️  说话人分离超时（>1小时），跳过")
        return
    except FileNotFoundError:
        print(f"⚠️  diarize.py 未找到，跳过")
        return
    print(f"  说话人分离耗时: {checkpoints._format_duration(time.time() - t0)}")

    if not diarization_output.exists():
        print(f"⚠️  分离结果未生成，跳过合并")
        return
    try:
        with open(diarization_output, "r", encoding="utf-8") as f:
            diar_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"⚠️  分离结果解析失败，跳过合并")
        return

    diar_segments = diar_data.get("segments", [])
    if not diar_segments:
        print(f"⚠️  分离结果无段落数据，跳过合并")
        return

    wjson = output_dir / "transcript.json"
    if not wjson.exists():
        return
    try:
        with open(wjson, "r", encoding="utf-8") as f:
            w_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    w_segments = w_data.get("segments", [])
    matched = 0
    for seg in w_segments:
        mid = (seg.get("start", 0) + seg.get("end", 0)) / 2
        for d in diar_segments:
            if d.get("text"):
                if abs(d["start"] - mid) < 2.0:
                    seg["speaker"] = d.get("speaker", "")
                    matched += 1
                    break
            else:
                if d["start"] <= mid <= d["end"]:
                    seg["speaker"] = d.get("speaker", "")
                    matched += 1
                    break

    with open(output_dir / "transcript_diarized.json", "w", encoding="utf-8") as f:
        json.dump(w_data, f, ensure_ascii=False, indent=2)
    speakers = set(s.get("speaker") for s in w_segments if s.get("speaker"))
    print(f"\n✅ 说话人标签已合并: {len(w_segments)} 段, {matched} 段匹配, {len(speakers)} 个说话人")


def run(
    input_path: str,
    output_dir: Path,
    config: dict[str, Any],
    settings: dict[str, Any],
    language: str,
    initial_prompt: str | None,
    diarization_cfg: dict[str, Any],
    num_speakers: int | None,
    diarize_method: str,
    device: str = "cpu",
) -> dict[str, Any]:
    """Whisper 主路径入口。

    Args:
        input_path: 输入音频绝对路径
        output_dir: 输出目录（已 mkdir）
        config: 三层合并后的全局 config
        settings: backend 专属 settings（含 binary / default_model）
        language: 语言代码（默认 zh）
        initial_prompt: 法律术语 prompt（whisper CLI --initial_prompt）
        diarization_cfg: {"enabled": bool, "speaker_method": ..., ...}
        num_speakers: 说话人数
        diarize_method: funasr | sherpa-onnx | whisperx
        device: cpu | cuda | mps | auto（v3.2+ 新增，Mac M-series 推荐 mps）

    Returns:
        dict 含 "exit_code" / "error" / "backend"
    """
    model = settings.get("default_model", "large-v3")
    binary = settings.get("binary") or _DEFAULT_WHISPER_BIN
    if not Path(binary).exists():
        binary = shutil.which("whisper") or binary
    print(f"\n🎤 Whisper CLI 后端: model={model}, language={language}, device={device}")
    print(f"  binary: {binary}")

    # Whisper CLI 默认用 CPU 跑 fp16 时会 OOM；按 device 决策
    # - cpu: 强制 fp16=False（CPU 不支持 fp16）
    # - cuda/mps: 允许 fp16=True（GPU 加速）
    # - auto: 让 Whisper 自己决定（不显式传 fp16）
    fp16_value: str | None
    if device == "cpu":
        fp16_value = "False"
    elif device in ("cuda", "mps"):
        fp16_value = "True"
    else:  # auto
        fp16_value = None

    cmd = [
        binary,
        str(Path(input_path).absolute()),
        "--model", model,
        "--language", language,
        "--output_format", "json",
        "--output_dir", str(output_dir),
        "--verbose", "True",
    ]
    if device != "auto":
        cmd += ["--device", device]
    if fp16_value is not None:
        cmd += ["--fp16", fp16_value]
    if initial_prompt:
        cmd += ["--initial_prompt", initial_prompt]

    t0 = time.time()
    try:
        process = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=checkpoints.MAX_DURATION_SECONDS + 600,
        )
    except subprocess.TimeoutExpired:
        print(f"\n❌ Whisper 转写超时")
        if device == "mps":
            print(f"  ⚠️  MPS 设备转写超时，自动 fallback CPU 重试")
            return run(
                input_path=input_path, output_dir=output_dir, config=config,
                settings=settings, language=language, initial_prompt=initial_prompt,
                diarization_cfg=diarization_cfg, num_speakers=num_speakers,
                diarize_method=diarize_method, device="cpu",
            )
        return {"error": "timeout", "backend": "whisper"}
    elapsed = time.time() - t0
    print(f"  Whisper 耗时: {checkpoints._format_duration(elapsed)}")

    if process.returncode != 0:
        stderr = process.stderr.strip()[-1500:]
        if "out of memory" in stderr.lower() or "OOM" in stderr:
            print(f"\n❌ Whisper OOM。换 small/base 重试")
        elif "ffmpeg" in stderr.lower():
            print(f"\n❌ ffmpeg 问题: brew install ffmpeg")

        # v3.2+ 容错：MPS 设备失败时自动 fallback CPU
        # （Whisper 0.6.0 对 Apple Silicon MPS 支持不完整，初始化卡住）
        if device == "mps":
            print(f"\n  ⚠️  MPS 设备转写失败，自动 fallback CPU 重试")
            return run(
                input_path=input_path, output_dir=output_dir, config=config,
                settings=settings, language=language, initial_prompt=initial_prompt,
                diarization_cfg=diarization_cfg, num_speakers=num_speakers,
                diarize_method=diarize_method, device="cpu",
            )
        return {"error": f"whisper 退出 {process.returncode}", "stderr": stderr, "backend": "whisper"}

    rename_whisper_outputs(output_dir, input_path)

    if diarization_cfg.get("enabled", True):
        _run_diarization_and_merge(input_path, output_dir, diarize_method, num_speakers)

    return {"elapsed": elapsed, "exit_code": 0, "backend": "whisper"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="asr_whisper.py — Whisper CLI 后端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例: python3 asr_whisper.py --input 录音.mp3 --num-speakers 2",
    )
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output-dir", "-o", default="./转写结果/")
    parser.add_argument("--whisper-model", default="large-v3", help="tiny/base/small/medium/large-v3/turbo")
    parser.add_argument("--whisper-device", default="cpu", choices=["cpu", "cuda", "mps", "auto"],
                        help="推理设备（v3.2+ 新增；Mac M-series 推荐 mps，速度 5-10 倍）")
    parser.add_argument("--language", "-l", default="zh")
    parser.add_argument("--initial-prompt", "-p", default=None)
    parser.add_argument("--num-speakers", "-n", type=int, default=None)
    parser.add_argument("--diarize-method", default="funasr", choices=["funasr", "sherpa-onnx", "whisperx"])
    parser.add_argument("--no-diarize", dest="diarize", action="store_false")
    args = parser.parse_args()

    cfg = load_global_config()
    settings = get_backend_settings(cfg, "whisper")
    settings["default_model"] = args.whisper_model
    diar_cfg = {"enabled": args.diarize}
    out = output_naming.make_output_dir(args.output_dir, "")
    print(f"\n📁 输出目录: {out}")

    cp1 = checkpoints.checkpoint_1_preflight(args.input)
    if not cp1["passed"]:
        return 1
    cp2 = checkpoints.checkpoint_2_backend_check("whisper", settings)
    if not cp2["passed"]:
        return 1
    cp2w = checkpoints.checkpoint_2_whisper_model(args.whisper_model)
    if not cp2w["info"].get("cached") and cp2w["info"].get("fallback_model"):
        print(f"\n  🔄 Whisper 降级: {args.whisper_model} → {cp2w['info']['fallback_model']}")
        settings["default_model"] = cp2w["info"]["fallback_model"]

    result = run(
        input_path=args.input,
        output_dir=out,
        config=cfg,
        settings=settings,
        language=args.language,
        initial_prompt=args.initial_prompt,
        diarization_cfg=diar_cfg,
        num_speakers=args.num_speakers,
        diarize_method=args.diarize_method,
        device=args.whisper_device,
    )

    if "error" in result:
        print(f"❌ {result['error']}")
        return 2

    write_transcribe_log(out, {
        "tool": "cn-evidence",
        "version": "3.2",
        "backend": "whisper",
        "model": settings.get("default_model"),
        "language": args.language,
        "input": args.input,
        "input_sha256": checkpoints._file_sha256(args.input),
        "elapsed_seconds": result.get("elapsed"),
        "output_dir": str(out),
    })
    cp3 = checkpoints.checkpoint_3_post_transcribe(out)
    print(f"\n✅ 转写完成。目录: {out}")
    return 0 if cp3["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
