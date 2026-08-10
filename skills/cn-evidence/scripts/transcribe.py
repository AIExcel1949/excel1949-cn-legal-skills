#!/usr/bin/env python3
"""
transcribe.py — 统一教学入口（cn-evidence v3.2）

仅做 3 件事：
  1) 三层 config 合并（defaults ← global ← case_info.json ← CLI）
  2) CHECKPOINT 1/2/3 + 输出目录创建
  3) 分派到对应 backend 脚本：

直接使用（按需）：
  - 默认走 paraformer-zh：
      python3 scripts/transcribe.py --input 录音.mp3 --num-speakers 2
  - 切到 Whisper：
      python3 scripts/transcribe.py --input 录音.mp3 --asr-backend whisper
  - 切到高精度 Fun-ASR-Nano：
      python3 scripts/transcribe.py --input 录音.mp3 --asr-backend funasr-nano
  - 切到多语种 SenseVoice：
      python3 scripts/transcribe.py --input 录音.mp3 --asr-backend sensevoice-small
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from _common import checkpoints, output_naming  # noqa: E402
from _common.output_naming import write_transcribe_log  # noqa: E402

import config as cfg_mod  # noqa: E402
from asr_whisper import run as run_whisper  # noqa: E402
from asr_whisper_turbo import run as run_whisper_turbo  # noqa: E402
from asr_paraformer import run as run_paraformer  # noqa: E402
from asr_funasr_nano import run as run_funasr_nano  # noqa: E402
from asr_sensevoice import run as run_sensevoice  # noqa: E402


BACKEND_RUNNERS: dict[str, Any] = {
    "whisper": run_whisper,
    "whisper-turbo": run_whisper_turbo,
    "paraformer-zh": run_paraformer,
    "funasr-nano": run_funasr_nano,
    "sensevoice-small": run_sensevoice,
}
"""backend -> run() 函数映射；dispatcher 据此分派。"""

KNOWN_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3", "turbo"]
"""Whisper 模型下拉选项（用于 --whisper-model + 向后兼容 --model）。"""


def _interactive_backend() -> str:
    print("\n" + "=" * 60)
    print("  请选择 ASR backend：")
    print("=" * 60)
    print("   1. paraformer-zh    本地中文默认档")
    print("   2. funasr-nano      方言、口音候选档，资源占用较高")
    print("   3. sensevoice-small 中粤英日韩多语种档")
    print("   4. whisper          Whisper 兼容档，模型可选")
    print("   5. whisper-turbo    Whisper 快速档")
    try:
        c = input("  请输入编号 [1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        c = ""
    return {
        "1": "paraformer-zh",
        "2": "funasr-nano",
        "3": "sensevoice-small",
        "4": "whisper",
        "5": "whisper-turbo",
    }.get(c, "paraformer-zh")


def _interactive_whisper_model() -> str:
    print("\n  请选择 Whisper 模型（仅当 backend=whisper）：")
    print("   1. medium         较小资源档")
    print("   2. large-v3       较高资源档")
    print("   3. turbo          快速档")
    try:
        c = input("  请输入编号 [2]: ").strip()
    except (EOFError, KeyboardInterrupt):
        c = ""
    return {"1": "medium", "2": "large-v3", "3": "turbo"}.get(c, "large-v3")


def run_dispatch(args: argparse.Namespace) -> int:
    """主流程：config merge → CHECKPOINTs → backend run → log → 总结。"""
    start = time.time()

    # 1) 三层 config 合并
    cli_args: dict[str, Any] = {
        "asr_backend": getattr(args, "asr_backend", None),
        "diarize": getattr(args, "diarize", None),
        "num_speakers": getattr(args, "num_speakers", None),
        "output_format": "json",
        "language": getattr(args, "language", None),
    }
    try:
        global_cfg = cfg_mod.load_global_config()
        case_info = cfg_mod.load_case_info(getattr(args, "case_info", None))
        cfg = cfg_mod.merge_config(global_cfg, case_info, cli_args)
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        print(f"   修复: python3 scripts/config.py init")
        return 1

    backend = cfg_mod.get_active_backend(cfg)
    settings = cfg_mod.get_backend_settings(cfg, backend)
    diar_cfg = cfg.get("diarization", {})
    language = cli_args.get("language") or case_info.get("language", "zh")

    banner = "=" * 60
    print(f"\n{banner}")
    print(f"  cn-evidence v3.2 — 多 backend dispatcher")
    print(f"{banner}")
    print(f"  输入: {args.input}")
    print(f"  输出: {args.output_dir}")
    print(f"  backend: {backend}")
    print(f"  语言: {language}")
    diar_method = diar_cfg.get("speaker_method", "cam++")
    print(f"  说话人分离: {'是 (' + diar_method + ')' if diar_cfg.get('enabled', True) else '否'}")
    print(f"  案件: {args.case_name or '(未指定)'}")
    print(f"{banner}")

    # 2) CHECKPOINT 1
    cp1 = checkpoints.checkpoint_1_preflight(args.input)
    if not cp1["passed"]:
        return 1

    # 3) CHECKPOINT 2 — backend 检查
    cp2 = checkpoints.checkpoint_2_backend_check(backend, settings)
    if not cp2["passed"]:
        print(f"\n❌ backend {backend} 未就位，无法继续")
        print(f"   修复: bash scripts/install.sh --backend {backend}")
        return 1
    # Whisper 路径加测模型缓存
    if backend == "whisper":
        cp2w = checkpoints.checkpoint_2_whisper_model(args.whisper_model)
        if not cp2w["info"].get("cached") and cp2w["info"].get("fallback_model"):
            print(f"\n  🔄 Whisper 降级: {args.whisper_model} → {cp2w['info']['fallback_model']}")
            args.whisper_model = cp2w["info"]["fallback_model"]
            settings["default_model"] = args.whisper_model

    # 4) 输出目录
    out = output_naming.make_output_dir(args.output_dir, args.case_name)
    print(f"\n📁 输出目录: {out}")

    # 5) 分派到 backend run()
    runner = BACKEND_RUNNERS[backend]
    if backend == "whisper":
        result = runner(
            input_path=args.input, output_dir=out, config=cfg, settings=settings,
            language=language, initial_prompt=args.initial_prompt,
            diarization_cfg=diar_cfg, num_speakers=args.num_speakers,
            diarize_method=args.diarize_method,
            device=args.whisper_device,
        )
    elif backend == "whisper-turbo":
        # Whisper Turbo 走自己的 thin wrapper（强制 settings["default_model"]="turbo"）
        result = runner(
            input_path=args.input, output_dir=out, config=cfg, settings=settings,
            language=language, initial_prompt=args.initial_prompt,
            diarization_cfg=diar_cfg, num_speakers=args.num_speakers,
            device=args.whisper_device,
        )
    else:
        result = runner(
            input_path=args.input, output_dir=out, config=cfg, settings=settings,
            language=language, initial_prompt=args.initial_prompt,
            diarization_cfg=diar_cfg, num_speakers=args.num_speakers,
        )

    if "error" in result:
        print(f"\n❌ backend {backend} 转写失败:")
        print(f"   {result['error']}")
        return 2

    elapsed = time.time() - start

    # 6) 转写日志
    log_data: dict[str, Any] = {
        "tool": "cn-evidence",
        "version": "3.2",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "input_file": str(Path(args.input).absolute()),
        "input_sha256": checkpoints._file_sha256(args.input),
        "asr_backend": backend,
        "language": language,
        "diarization": diar_cfg,
        "output_dir": str(out),
        "duration_seconds": round(elapsed, 1),
    }
    if backend == "whisper":
        log_data["whisper_model"] = settings.get("default_model")
    write_transcribe_log(out, log_data)

    # 7) CHECKPOINT 3
    cp3 = checkpoints.checkpoint_3_post_transcribe(out)

    # 8) 总结
    print(f"\n{banner}")
    print(f"✅ 转写完成 (backend={backend})" if cp3["passed"] else f"⚠️  完成但有警告")
    print(f"{banner}")
    print(f"  输出: {out}")
    print(f"  耗时: {checkpoints._format_duration(elapsed)}")
    print(f"\n  下一步:")
    json_file = "transcript_diarized.json" if diar_cfg.get("enabled", True) else "transcript.json"
    print(f"    python3 scripts/format_transcript.py \\")
    print(f"      --input {out}/{json_file} \\")
    print(f"      --output 文字稿.md \\")
    print(f"      --case-info case_info.json")
    print(f"\n  💡 配置管理:")
    print(f"    python3 scripts/config.py doctor     # 5 backend 就位检查")
    return 0 if cp3["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="transcribe.py v3.2 — 录音证据转写 dispatcher（5 backend 可选）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  默认（paraformer-zh）
    python3 scripts/transcribe.py --input 录音.mp3 --num-speakers 2

  切到 Whisper（向后兼容老调用）
    python3 scripts/transcribe.py --input 录音.mp3 \\
      --asr-backend whisper --whisper-model large-v3

  切到高精度 Fun-ASR-Nano
    python3 scripts/transcribe.py --input 录音.mp3 --asr-backend funasr-nano

  切到多语种 SenseVoice-Small
    python3 scripts/transcribe.py --input 录音.mp3 --asr-backend sensevoice-small

  交互式选择 backend
    python3 scripts/transcribe.py --input 录音.mp3 --interactive
        """,
    )
    parser.add_argument("--input", "-i", required=True, help="输入音频文件路径（mp3/wav/m4a/mp4）")
    parser.add_argument("--output-dir", "-o", default="./转写结果/", help="输出目录")
    parser.add_argument("--asr-backend", "-B", default=None, choices=list(BACKEND_RUNNERS.keys()),
                        help="ASR backend（默认从 config 读取；v3.2 默认 paraformer-zh）")
    parser.add_argument("--whisper-model", default=None, choices=KNOWN_WHISPER_MODELS,
                        help="仅当 --asr-backend=whisper 时生效")
    parser.add_argument("--whisper-device", default="cpu", choices=["cpu", "cuda", "mps", "auto"],
                        help="Whisper 推理设备（v3.2+ 新增；Mac M-series 推荐 mps，速度 5-10 倍）")
    parser.add_argument("--model", "-m", default=None, choices=KNOWN_WHISPER_MODELS,
                        help="【向后兼容】触发 Whisper backend；如指定 --model 不传 --asr-backend，自动切到 --asr-backend whisper")
    parser.add_argument("--language", "-l", default="zh", help="音频语言代码")
    parser.add_argument("--case-name", "-c", default="", help="案件名（用于输出子目录命名）")
    parser.add_argument("--case-info", default=None, help="案例级 case_info.json（覆盖全局配置）")
    parser.add_argument("--initial-prompt", "-p", default=None,
                        help="首窗口提示词（Whisper 直接 / FunASR 转 hotword）")
    parser.add_argument("--diarize", dest="diarize", action="store_true", default=None, help="启用说话人分离")
    parser.add_argument("--no-diarize", dest="diarize", action="store_false", help="禁用说话人分离")
    parser.add_argument("--diarize-method", default="funasr",
                        choices=["funasr", "sherpa-onnx", "whisperx"],
                        help="说话人分离方法（Whisper 路径专属；FunASR 路径内置 cam++）")
    parser.add_argument("--num-speakers", "-n", type=int, default=None, help="指定说话人数")
    parser.add_argument("--interactive", action="store_true", help="交互式选择 backend")
    args = parser.parse_args()

    # 向后兼容
    if args.model and not args.asr_backend:
        print(f"⚠️  兼容性提示: --model={args.model} 未指定 --asr-backend，自动切到 --asr-backend whisper")
        args.asr_backend = "whisper"
        if not args.whisper_model:
            args.whisper_model = args.model
    if args.asr_backend == "whisper" and not args.whisper_model:
        try:
            cfg = cfg_mod.load_global_config()
            args.whisper_model = cfg.get("backends", {}).get("whisper", {}).get("default_model", "large-v3")
        except Exception:
            args.whisper_model = "large-v3"

    if args.interactive and not args.asr_backend:
        args.asr_backend = _interactive_backend()
        if args.asr_backend == "whisper" and not args.whisper_model:
            args.whisper_model = _interactive_whisper_model()

    return run_dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
