"""输出目录命名 + 日志写入 — v3.2 共享层
保证 4 个 backend 脚本产出路径一致。
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def make_output_dir(output_dir: str | Path, case_name: str = "") -> Path:
    """创建输出目录。如有 case_name 加时间戳子目录；失败兜底到 /tmp。

    Args:
        output_dir: 父目录
        case_name: 案件名（影响子目录命名）

    Returns:
        最终输出目录路径（已创建）
    """
    try:
        out = Path(output_dir)
        if case_name:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = "".join(c for c in case_name if c.isalnum() or c in "_- ").strip()[:50]
            out = out / f"{safe}_{ts}"
        out.mkdir(parents=True, exist_ok=True)
        return out
    except (OSError, PermissionError) as e:
        print(f"\n❌ 无法创建输出目录: {output_dir}")
        print(f"  错误: {e}")
        fb = Path(tempfile.mkdtemp(prefix="cne_output_"))
        print(f"  💡 降级到: {fb}")
        return fb


def rename_whisper_outputs(output_dir: Path, input_path: str) -> None:
    """Whisper 默认输出 `<stem>.*` 重命名为 `transcript.*`。

    多格式 (.json/.txt/.vtt/.srt/.tsv)；失败时忽略，继续运行。
    """
    input_stem = Path(input_path).stem
    for ext in (".json", ".txt", ".vtt", ".srt", ".tsv"):
        default = output_dir / f"{input_stem}{ext}"
        target = output_dir / f"transcript{ext}"
        if default.exists() and default != target:
            try:
                shutil.move(str(default), str(target))
            except OSError as e:
                print(f"⚠️  重命名失败: {default.name} -> {target.name}: {e}")


def write_transcribe_log(output_dir: Path, log_data: dict[str, Any]) -> Path:
    """写入 transcribe.log。"""
    log_file = output_dir / "transcribe.log"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    return log_file


def write_transcript_json(output_dir: Path, data: dict[str, Any]) -> Path:
    """写入 transcript.json（统一 paths）。"""
    out = output_dir / "transcript.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out


def write_transcript_diarized_json(output_dir: Path, data: dict[str, Any]) -> Path:
    """写入 transcript_diarized.json。"""
    out = output_dir / "transcript_diarized.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out
