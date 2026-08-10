#!/usr/bin/env python3
"""
asr_sensevoice.py — SenseVoice-Small 后端（cn-evidence v3.2）

阿里达摩院多语种 + 情感事件 ASR：
- 支持中/粤/英/日/韩
- 输出含 <|zh|><|HAPPY|><|Speech|>... 结构化情感/事件 token
- 适合跨境案件（粤语当事人、英语对话）+ 非语义事件识别
- ModelScope 仓库: iic/SenseVoiceSmall（~896MB）
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
    """SenseVoice-Small 主路径入口 — 委托 funasr_runner。

    区别于 paraformer-zh：
    - SenseVoice 自带标点恢复（funasr_runner 自动跳过 punc_model）
    - 输出 token 含语言/情感标签，但 _common/funasr_runner 的 schema 转换只取 text 字段
    - 如需保留原始标签供研究，参看输出目录中 transcript.json 的 "raw_segments" 字段
    """
    return run_funasr_family(
        input_path=input_path,
        output_dir=output_dir,
        backend_name="sensevoice-small",
        settings=settings,
        language=language,
        initial_prompt=initial_prompt,
        num_speakers=num_speakers,
        diarization_cfg=diarization_cfg,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="asr_sensevoice.py — SenseVoice-Small 后端（多语种档）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例: python3 asr_sensevoice.py --input 录音.mp3 --num-speakers 2",
    )
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output-dir", "-o", default="./转写结果/")
    parser.add_argument("--language", "-l", default="zh")
    parser.add_argument("--initial-prompt", "-p", default=None)
    parser.add_argument("--num-speakers", "-n", type=int, default=None)
    parser.add_argument("--no-diarize", dest="diarize", action="store_false")
    args = parser.parse_args()

    cfg = load_global_config()
    settings = get_backend_settings(cfg, "sensevoice-small")
    diar_cfg = {"enabled": args.diarize}
    out = output_naming.make_output_dir(args.output_dir, "")
    print(f"\n📁 输出目录: {out}")

    cp1 = checkpoints.checkpoint_1_preflight(args.input)
    if not cp1["passed"]:
        return 1
    cp2 = checkpoints.checkpoint_2_backend_check("sensevoice-small", settings)
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
        "backend": "sensevoice-small",
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
