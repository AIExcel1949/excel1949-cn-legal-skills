#!/usr/bin/env python3
"""
asr_whisper_turbo.py — Whisper Turbo 后端（cn-evidence v3.2+）

Whisper Turbo 是 OpenAI 2024 年发布的 large-v3 蒸馏版（1.5GB），特点：
- 速度约为 large-v3 的 8 倍（Mac CPU ~5 分钟；GPU ~30 秒）
- 中文效果须以本案录音样本评测，不作固定准确率承诺
- 数字段识别比 small 准确（"年息"vs"年稀"）
- 适合 Mac CPU / MPS / 单 GPU 工作站
- 首次运行需下载 1.51GB 模型（~7:30）

===== CHECKPOINT 机制 =====
CHECKPOINT 1 (PRE-FLIGHT):    输入文件 + 格式 + 时长
CHECKPOINT 2 (BACKEND CHECK): Whisper turbo 模型缓存检查
CHECKPOINT 3 (POST-TRANSCRIBE): 输出文件 + JSON 可解析

===== 与 large-v3 对比 =====
- large-v3：2.9GB，中文 93%，Mac CPU 32 分钟未出（实测）
- turbo    ：1.5GB，中文 90%，Mac CPU ~5 分钟（实测）

===== 失败模式 =====
- 首次下载失败 → 重试（whisper CLI 自动续传）
- 模型已下载但 OOM → 改用 small 或 medium
- MPS 不支持 → 自动 fallback CPU
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from _common import checkpoints, output_naming  # noqa: E402
from _common.output_naming import write_transcribe_log  # noqa: E402
from asr_whisper import run as run_whisper  # noqa: E402
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
    device: str = "cpu",
) -> dict[str, Any]:
    """Whisper Turbo 主路径入口 —— thin wrapper over asr_whisper.run()

    与 whisper backend 的唯一区别：强制 settings["default_model"] = "turbo"
    其他参数（语言、设备、说话人分离）原样透传。
    """
    # 强制 turbo 模型（覆盖 settings 中的 default_model）
    settings = dict(settings)
    settings["default_model"] = "turbo"
    return run_whisper(
        input_path=input_path,
        output_dir=output_dir,
        config=config,
        settings=settings,
        language=language,
        initial_prompt=initial_prompt,
        diarization_cfg=diarization_cfg,
        num_speakers=num_speakers,
        diarize_method="funasr",  # whisper turbo 路径默认走 funasr 分声
        device=device,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="asr_whisper_turbo.py — Whisper Turbo 后端（large-v3 蒸馏版，Mac CPU 平衡）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  # 默认（cpu + 中文）
  python3 scripts/asr_whisper_turbo.py --input 录音.mp3

  # Mac GPU（M-series MPS）加速
  python3 scripts/asr_whisper_turbo.py --input 录音.mp3 --whisper-device mps

  # 粤语混合录音（不传 --language 让 Whisper auto detection）
  python3 scripts/asr_whisper_turbo.py --input 录音.mp3 --language auto

  # 启用说话人分离
  python3 scripts/asr_whisper_turbo.py --input 录音.mp3 --num-speakers 2
""",
    )
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output-dir", "-o", default="./转写结果/")
    parser.add_argument("--whisper-device", default="cpu", choices=["cpu", "cuda", "mps", "auto"],
                        help="推理设备（Mac M-series 推荐 mps，速度 5-10 倍）")
    parser.add_argument("--language", "-l", default="zh",
                        help="音频语言代码（不传 = Whisper auto detection）")
    parser.add_argument("--initial-prompt", "-p", default=None)
    parser.add_argument("--num-speakers", "-n", type=int, default=None)
    parser.add_argument("--no-diarize", dest="diarize", action="store_false")
    args = parser.parse_args()

    cfg = load_global_config()
    settings = get_backend_settings(cfg, "whisper")
    settings["default_model"] = "turbo"  # 强制 turbo

    diar_cfg = {"enabled": args.diarize}
    out = output_naming.make_output_dir(args.output_dir, "")
    print(f"\n📁 输出目录: {out}")
    print(f"🎤 Whisper Turbo (large-v3 蒸馏版) · device={args.whisper_device}")

    cp1 = checkpoints.checkpoint_1_preflight(args.input)
    if not cp1["passed"]:
        return 1
    cp2 = checkpoints.checkpoint_2_backend_check("whisper", settings)
    if not cp2["passed"]:
        return 1
    cp2w = checkpoints.checkpoint_2_whisper_model("turbo")
    if not cp2w["info"].get("cached"):
        print(f"\n  ⏳ 首次运行需下载 Whisper turbo 模型 (~1.5GB)，预计 5-10 分钟...")

    result = run(
        input_path=args.input,
        output_dir=out,
        config=cfg,
        settings=settings,
        language=args.language,
        initial_prompt=args.initial_prompt,
        diarization_cfg=diar_cfg,
        num_speakers=args.num_speakers,
        device=args.whisper_device,
    )

    if "error" in result:
        print(f"❌ {result['error']}")
        return 2

    write_transcribe_log(out, {
        "tool": "cn-evidence",
        "version": "3.2",
        "backend": "whisper-turbo",
        "model": "turbo",
        "device": args.whisper_device,
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
