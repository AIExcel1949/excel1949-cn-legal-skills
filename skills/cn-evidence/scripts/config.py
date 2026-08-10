#!/usr/bin/env python3
"""
配置加载 — cn-evidence v3.2

三层配置合并（后覆盖前）：
    defaults  <-  ~/.config/cn-evidence-transcribe/config.yaml  <-  case_info.json  <-  CLI 参数

CLI 入口:
    python3 scripts/config.py init     # 生成默认全局配置
    python3 scripts/config.py show     # 显示当前生效的全局配置
    python3 scripts/config.py doctor   # 检查当前后端模型是否就位

依赖: PyYAML（请在本 Skill 的 .venv 中安装）
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        "❌ scripts/config.py 需要 PyYAML。运行: "
        "请先运行 bash scripts/install.sh，或在 .venv 中安装 pyyaml。\n"
    )
    raise SystemExit(2) from exc


# ============================================================
# 常量
# ============================================================

ASR_BACKENDS: tuple[str, ...] = (
    "whisper",
    "whisper-turbo",
    "paraformer-zh",
    "funasr-nano",
    "sensevoice-small",
)
"""用户决策保留的 5 个 ASR backend。
- whisper        : 向后兼容 opt-in（OpenAI Whisper CLI，可选 large-v3/medium/small/...）
- whisper-turbo  : v3.2+ 新增（large-v3 的快速版）
- paraformer-zh  : v3.0+ 默认本地中文后端
- funasr-nano    : 方言与口音档（800M，资源占用较高，需以本案样本评测）
- sensevoice-small: 多语种档（中粤英日韩 + 情感事件）
"""

DEFAULT_BACKEND: str = "paraformer-zh"
"""v3.0 起默认 backend。用户决策：'FunASR 不需要 whisper 模型'。"""

KNOWN_WHISPER_TURBO_MODELS: tuple[str, ...] = ("turbo",)
"""Whisper Turbo 后端固定使用 'turbo' 模型（large-v3 蒸馏版）。"""

WHISPER_MODEL_CACHE_FILES: dict[str, str] = {
    "tiny": "tiny.pt",
    "base": "base.pt",
    "small": "small.pt",
    "medium": "medium.pt",
    "large-v3": "large-v3.pt",
    "turbo": "large-v3-turbo.pt",  # Whisper CLI 实际缓存的文件名
}
"""Whisper 模型名 → 缓存文件名的映射（v3.2+ 新增）。
Whisper CLI 不直接以 model 名为文件名缓存（如 turbo 缓存为 large-v3-turbo.pt）。"""

GLOBAL_CONFIG_PATH: Path = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "cn-evidence-transcribe" / "config.yaml"
"""全局配置默认位置（受 XDG_CONFIG_HOME 影响）。"""

SKILL_ROOT: Path = Path(__file__).resolve().parent.parent
DEFAULT_WHISPER_BINARY: str = str(SKILL_ROOT / ".venv" / "bin" / "whisper")
"""安装脚本统一创建 .venv，Whisper CLI 默认从该虚拟环境调用。"""

DIARIZATION_METHODS: tuple[str, ...] = ("cam++", "sherpa-onnx", "whisperx")
"""说话人分离方法（diarize.py 仍支持 sherpa-onnx / whisperx，作为 opt-in 保留）。"""

# ============================================================
# 默认 backend 配置（首次运行时写入 global config）
# ============================================================

DEFAULT_BACKEND_CONFIG: dict[str, dict[str, Any]] = {
    "whisper": {
        "binary": DEFAULT_WHISPER_BINARY,
        "cache_dir": str(Path.home() / ".cache" / "whisper"),
        "default_model": "large-v3",
        "auto_download": True,
        "min_memory_gb": 1,
        "note": "OpenAI Whisper CLI。向后兼容路径，新部署请优先用 paraformer-zh",
    },
    "whisper-turbo": {
        "binary": DEFAULT_WHISPER_BINARY,
        "cache_dir": str(Path.home() / ".cache" / "whisper"),
        "default_model": "turbo",  # 固定为 turbo（large-v3 蒸馏版）
        "auto_download": True,
        "min_memory_gb": 2,
        "note": "Whisper Turbo 快速档。速度和错误率受设备、时长、噪声和口音影响，须用本案样本评测",
    },
    "paraformer-zh": {
        "repo_id": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "cache_dir": str(Path.home() / ".cache" / "modelscope" / "iic"),
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
        "spk_model": "cam++",
        "auto_download": True,
        "min_memory_gb": 1,
        "note": "默认本地中文后端。实际错误率受噪声、方言、设备和场景影响，必须人工回听",
    },
    "funasr-nano": {
        "repo_id": "FunAudioLLM/Fun-ASR-Nano-2512",
        "cache_dir": str(Path.home() / ".cache" / "modelscope" / "FunAudioLLM"),
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
        "spk_model": "cam++",
        "auto_download": False,
        "min_memory_gb": 6,
        "note": "Fun-ASR-Nano-2512（800M）。建议预留较多内存；实际准确率必须以本案录音抽样评测",
    },
    "sensevoice-small": {
        "repo_id": "iic/SenseVoiceSmall",
        "cache_dir": str(Path.home() / ".cache" / "modelscope" / "iic"),
        "vad_model": "fsmn-vad",
        "spk_model": "cam++",
        "auto_download": False,
        "min_memory_gb": 1,
        "note": "多语种档：中粤英日韩 + 情感事件标签。适合跨境案件",
    },
}


# ============================================================
# 全局配置生成与读取
# ============================================================

def generate_default_config() -> dict[str, Any]:
    """生成默认全局配置。"""
    return {
        "asr_backend": DEFAULT_BACKEND,
        "backends": {
            name: dict(cfg) for name, cfg in DEFAULT_BACKEND_CONFIG.items()
        },
        "diarization": {
            "enabled": True,
            "speaker_method": "cam++",
            "default_num_speakers": None,  # None = 自动推断
        },
        "output": {
            "format": "both",  # md | docx | both
            "template_path": "assets/录音文字稿-模板.docx",
        },
    }


def save_default_config_if_missing(path: Path | None = None) -> Path:
    """若指定路径不存在则写入默认模板。返回文件路径。"""
    target = Path(path) if path else GLOBAL_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        cfg = generate_default_config()
        with open(target, "w", encoding="utf-8") as f:
            f.write(
                "# cn-evidence v3.2 全局配置\n"
                "# 案例级 case_info.json 字段级覆盖此文件；CLI 参数最高优先级。\n"
                "# 修改后下一次运行 transcribe.py 时生效。\n\n"
            )
            yaml.dump(cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return target


def load_global_config(path: Path | None = None) -> dict[str, Any]:
    """加载全局 config.yaml；不存在则生成默认。返回 dict。"""
    target = save_default_config_if_missing(path)
    with open(target, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # 兜底：若文件被清空
    if not cfg:
        cfg = generate_default_config()
    return cfg


def load_case_info(case_info_path: str | Path | None) -> dict[str, Any]:
    """加载案例级 case_info.json；不存在或路径为空返回空字典。"""
    if not case_info_path:
        return {}
    p = Path(case_info_path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 三层配置合并
# ============================================================

def merge_config(
    global_cfg: dict[str, Any],
    case_info: dict[str, Any],
    cli_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """三层合并：defaults <- global_cfg <- case_info <- cli_args.

    Returns:
        合并后的配置 dict：
          - asr_backend (str)
          - backends (dict)
          - diarization (dict)
          - output (dict)
    """
    # 深复制避免原地修改
    merged: dict[str, Any] = {
        "asr_backend": global_cfg.get("asr_backend", DEFAULT_BACKEND),
        "backends": {k: dict(v) for k, v in global_cfg.get("backends", {}).items()},
        "diarization": dict(global_cfg.get("diarization", {})),
        "output": dict(global_cfg.get("output", {})),
    }

    # 1) 案例级 asr_backend 覆盖
    if isinstance(case_info, dict) and "asr_backend" in case_info:
        merged["asr_backend"] = case_info["asr_backend"]
    # 2) 案例级 diarization 块覆盖
    if isinstance(case_info, dict) and isinstance(case_info.get("diarization"), dict):
        merged["diarization"].update(case_info["diarization"])
    # 3) CLI 覆盖（最高优先级）
    if cli_args:
        if cli_args.get("asr_backend"):
            merged["asr_backend"] = cli_args["asr_backend"]
        if cli_args.get("diarize") is True:
            merged["diarization"]["enabled"] = True
        elif cli_args.get("diarize") is False:
            merged["diarization"]["enabled"] = False
        if cli_args.get("num_speakers"):
            merged["diarization"]["default_num_speakers"] = cli_args["num_speakers"]
        if cli_args.get("output_format"):
            merged["output"]["format"] = cli_args["output_format"]
        if cli_args.get("language"):
            # 语言不是合并项，但保留供下游使用
            merged["language"] = cli_args["language"]

    # 校验 asr_backend 合法
    if merged["asr_backend"] not in ASR_BACKENDS:
        raise ValueError(
            f"无效的 asr_backend='{merged['asr_backend']}'。"
            f"可选：{', '.join(ASR_BACKENDS)}（默认: {DEFAULT_BACKEND}）"
        )
    return merged


# ============================================================
# Backend 配置查询
# ============================================================

def get_active_backend(config: dict[str, Any]) -> str:
    """获取当前激活的 backend 名（兜底返回 DEFAULT_BACKEND）。"""
    return config.get("asr_backend", DEFAULT_BACKEND)


def get_backend_settings(config: dict[str, Any], backend_name: str | None = None) -> dict[str, Any]:
    """获取 backend 的具体设置（独立 dict 副本）。"""
    name = backend_name or get_active_backend(config)
    settings = config.get("backends", {}).get(name, {})
    if not settings:
        # 兜底返回内置默认
        settings = dict(DEFAULT_BACKEND_CONFIG.get(name, {}))
    else:
        settings = dict(settings)
    return settings


def is_backend_ready(config: dict[str, Any], backend_name: str | None = None) -> tuple[bool, str]:
    """检查 backend 模型是否已就位。返回 (bool, message)。"""
    name = backend_name or get_active_backend(config)
    settings = get_backend_settings(config, name)

    if name in ("whisper", "whisper-turbo"):
        cache_dir = Path(os.path.expanduser(settings.get("cache_dir", "~/.cache/whisper")))
        binary = settings.get("binary") or "whisper"
        resolved_binary = binary if os.path.exists(binary) else _which("whisper")
        if not resolved_binary:
            return False, f"Whisper CLI 未找到: {binary}"
        default_model = "large-v3" if name == "whisper" else "turbo"
        model_name = settings.get("default_model", default_model)
        # Whisper CLI 实际缓存文件名可能与 model 名不同（turbo → large-v3-turbo.pt）
        cache_filename = WHISPER_MODEL_CACHE_FILES.get(model_name, f"{model_name}.pt")
        model_file = cache_dir / cache_filename
        if not model_file.exists():
            return False, (
                f"Whisper 模型未缓存: {model_file}\n"
                f"  请运行: WHISPER_MODEL={model_name} bash scripts/install_whisper.sh"
            )
        return True, f"Whisper 模型已就绪: {model_file}"

    # FunASR 系 backend：检查 ModelScope 仓库实际目录（按完整 repo_id 路径）
    repo_id = settings.get("repo_id", "")
    if not repo_id or "/" not in repo_id:
        return False, f"backend={name} 缺少 repo_id 配置"
    # ModelScope 默认 cache 结构：~/.cache/modelscope/{完整 repo_id}/
    expected_dir = Path.home() / ".cache" / "modelscope" / repo_id
    if not expected_dir.exists():
        return False, (
            f"backend={name} 模型目录不存在: {expected_dir}\n"
            f"  触发下载: python3 -c \"from modelscope import snapshot_download; snapshot_download('{repo_id}')\""
        )
    # 检查关键权重文件存在
    has_weights = any(expected_dir.rglob("model.pt")) or any(expected_dir.rglob("*.bin"))
    if not has_weights:
        return False, f"backend={name} 权重文件缺失: {expected_dir}\n  repo_id={repo_id}"
    return True, f"backend={name} 已就绪: {expected_dir}"


def _which(name: str) -> str | None:
    """类似 shutil.which 但更宽容（兼容路径软链）。"""
    import shutil as _sh
    return _sh.which(name)


# ============================================================
# CLI 入口
# ============================================================

def cmd_init(args: argparse.Namespace) -> int:
    path = save_default_config_if_missing(args.path)
    print(f"✅ 全局配置: {path}")
    print(f"   可用 backend: {', '.join(ASR_BACKENDS)}")
    print(f"   默认 backend: {DEFAULT_BACKEND}")
    print("\n如需自定义，请编辑此文件后保存；案例级 case_info.json 字段可覆盖。")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    cfg = load_global_config(args.path)
    backend = get_active_backend(cfg)
    print(f"global config: {args.path or GLOBAL_CONFIG_PATH}")
    print(f"  active backend: {backend}")
    print(f"  diarization: {cfg.get('diarization')}")
    print(f"  output: {cfg.get('output')}")
    print(f"  backends keys: {list(cfg.get('backends', {}).keys())}")
    ready, msg = is_backend_ready(cfg, backend)
    mark = "✅" if ready else "⚠️ "
    print(f"  {mark} {backend}: {msg}")
    return 0 if ready else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_global_config(args.path)
    print(f"Doctor: 检查 {len(ASR_BACKENDS)} 个 backend 就位状态…")
    all_ok = True
    for name in ASR_BACKENDS:
        ready, msg = is_backend_ready(cfg, name)
        mark = "✅" if ready else "⚠️ "
        print(f"  {mark} {name}: {msg}")
        all_ok = all_ok and ready
    if all_ok:
        print("\n所有 backend 模型已就位。")
        return 0
    print("\n部分 backend 模型缺失，参考 install.sh --backend=<name> 下载。")
    return 1


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="cn-evidence 配置管理（v3.2）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path", type=Path, default=None,
        help="配置文件路径（默认: ~/.config/cn-evidence-transcribe/config.yaml）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="生成默认全局配置")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("show", help="显示当前全局配置 + 后端就位状态")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("doctor", help="全后端健康检查")
    sp.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
