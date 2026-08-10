#!/usr/bin/env python3
"""
asr_funasr_nano.py — Fun-ASR-Nano 后端（cn-evidence v3.2）

FunAudioLLM 多方言 ASR（800M），适合：
- 口音/方言/远场/多说话人
- 需要结合热词并做人工回听的录音
ModelScope 仓库: FunAudioLLM/Fun-ASR-Nano-2512（~2GB）

注意：需 ≥6GB 显存/MPS；Mac M-series CPU 推理较慢。Mac 默认 false-下载。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from _common import checkpoints, output_naming  # noqa: E402
from _common.funasr_runner import run_funasr_family  # noqa: E402
from _common.output_naming import write_transcribe_log  # noqa: E402
from config import get_backend_settings, load_global_config  # noqa: E402


def run(
    input_path: str,
    output_dir: Path,
    config: dict[str, Any],
    settings: dict[str, Any],
    language: str,
    initial_prompt: str | None,
    diarization_cfg: dict[str, Any],
    num_speakers: int | None,
) -> dict[str, Any]:
    """Fun-ASR-Nano 主路径入口 — 委托 funasr_runner。

    与 paraformer-zh 共享 _common/funasr_runner.run_funasr_family 实现，
    区别仅在 settings dict 和生成期参数。
    """
    return run_funasr_family(
        input_path=input_path,
        output_dir=output_dir,
        backend_name="funasr-nano",
        settings=settings,
        language=language,
        initial_prompt=initial_prompt,
        num_speakers=num_speakers,
        diarization_cfg=diarization_cfg,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="asr_funasr_nano.py — Fun-ASR-Nano 后端（高精度档）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例: python3 asr_funasr_nano.py --input 录音.mp3 --num-speakers 2",
    )
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output-dir", "-o", default="./转写结果/")
    parser.add_argument("--language", "-l", default="zh")
    parser.add_argument("--initial-prompt", "-p", default=None)
    parser.add_argument("--num-speakers", "-n", type=int, default=None)
    parser.add_argument("--no-diarize", dest="diarize", action="store_false")
    args = parser.parse_args()

    cfg = load_global_config()
    settings = get_backend_settings(cfg, "funasr-nano")

    # 资源门槛检测
    if settings.get("min_memory_gb", 0) >= 6:
        try:
            import psutil  # type: ignore
            avail_gb = psutil.virtual_memory().available / 1024 / 1024 / 1024
            if avail_gb < 6 and not settings.get("auto_download"):
                print(f"⚠️  Fun-ASR-Nano 需 ≥6GB 可用内存，当前 {avail_gb:.1f}GB。性能可能受限。")
        except ImportError:
            pass  # psutil 未装时跳过内存检查，不阻断流程

    diar_cfg = {"enabled": args.diarize}
    out = output_naming.make_output_dir(args.output_dir, "")
    print(f"\n📁 输出目录: {out}")

    cp1 = checkpoints.checkpoint_1_preflight(args.input)
    if not cp1["passed"]:
        return 1
    cp2 = checkpoints.checkpoint_2_backend_check("funasr-nano", settings)
    if not cp2["passed"]:
        return 1

    result = run(
        input_path=args.input, output_dir=out, config=cfg, settings=settings,
        language=args.language, initial_prompt=args.initial_prompt,
        diarization_cfg=diar_cfg, num_speakers=args.num_speakers,
    )

    if "error" in result:
        print(f"❌ {result['error']}")
        return 2

    write_transcribe_log(out, {
        "tool": "cn-evidence",
        "version": "3.2",
        "backend": "funasr-nano",
        "language": args.language,
        "input": args.input,
        "input_sha256": checkpoints._file_sha256(args.input),
        "elapsed_seconds": result.get("elapsed"),
        "segments_count": result.get("segments_count"),
        "speakers": result.get("speakers"),
        "output_dir": str(out),
    })
    cp3 = checkpoints.checkpoint_3_post_transcribe(out)
    print(f"\n✅ 转写完成。目录: {out}")
    return 0 if cp3["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
