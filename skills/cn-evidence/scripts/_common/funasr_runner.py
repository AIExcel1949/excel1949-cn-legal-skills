"""FunASR 系列 backend 共享实现 — v3.2 共享层
被 asr_paraformer.py / asr_funasr_nano.py / asr_sensevoice.py 共用。

Schema 兼容矩阵：
- paraformer-zh:  sentence_info[i] = {start, end, text, spk}
- funasr-nano:    sentence_info[i] = {start, end, text, spk}  （同 paraformer）
- sensevoice-small: sentence_info[i] = {start, end, sentence, timestamp, spk}
                    且 sentence 字段含 special tokens `<|yue|><|EMO_xxx|><|Speech|><|woitn|>`
                    —— 需要在下游统一清理
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .output_naming import (  # 相对导入：_common 包内模块
    write_transcript_diarized_json,
    write_transcript_json,
)


def _build_automodel_kwargs(
    backend_name: str,
    settings: dict[str, Any],
    diarization_enabled: bool,
) -> dict[str, Any]:
    """构造 funasr.AutoModel(...) kwargs。"""
    kwargs: dict[str, Any] = {"model": settings.get("repo_id", "")}
    if settings.get("vad_model"):
        kwargs["vad_model"] = settings["vad_model"]
    if backend_name != "sensevoice-small" and settings.get("punc_model"):
        kwargs["punc_model"] = settings["punc_model"]
    if diarization_enabled and settings.get("spk_model"):
        kwargs["spk_model"] = settings["spk_model"]
    if backend_name == "funasr-nano":
        kwargs["trust_remote_code"] = True
    return kwargs


def _build_generate_kwargs(
    backend_name: str,
    language: str,
    initial_prompt: str | None,
) -> dict[str, Any]:
    """构造 model.generate(...) kwargs。热词属于生成期参数。"""
    kwargs: dict[str, Any] = {}
    if backend_name == "funasr-nano":
        language_map = {"zh": "中文", "en": "英文", "ja": "日文"}
        kwargs.update({"cache": {}, "batch_size": 1, "language": language_map.get(language, language)})
        if initial_prompt:
            kwargs["hotwords"] = [
                item.strip()
                for item in re.split(r"[,，、;\n]", initial_prompt)
                if item.strip()
            ]
    elif backend_name == "sensevoice-small":
        supported = {"zh", "yue", "en", "ja", "ko", "auto"}
        kwargs["language"] = language if language in supported else "auto"
    elif initial_prompt:
        kwargs["hotword"] = initial_prompt
    return kwargs


def run_funasr_family(
    input_path: str,
    output_dir: Path,
    backend_name: str,  # "paraformer-zh" | "funasr-nano" | "sensevoice-small"
    settings: dict[str, Any],
    language: str = "zh",
    initial_prompt: str | None = None,
    num_speakers: int | None = None,
    diarization_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """运行指定 FunASR 系列 backend，一站式 ASR + 说话人分离。

    Returns:
        dict 包含 "backend" / "elapsed" / "segments_count" / "speakers" /
                "exit_code" 或 "error"。
    """
    if diarization_cfg is None:
        diarization_cfg = {"enabled": True}

    print(f"\n🎤 FunASR backend: {backend_name}")
    print(f"  repo: {settings.get('repo_id')}")

    try:
        from funasr import AutoModel  # type: ignore
    except ImportError:
        return {
            "error": "FunASR 未装。运行: pip install funasr torch torchaudio --break-system-packages",
        }

    diarization_enabled = bool(diarization_cfg.get("enabled", True))
    kwargs = _build_automodel_kwargs(backend_name, settings, diarization_enabled)
    print(f"  模型参数: {list(kwargs.keys())}")
    print(f"  首次运行将自动下载模型…")

    t0 = time.time()
    try:
        model = AutoModel(**kwargs)
    except Exception as e:
        return {"error": f"FunASR 模型加载失败: {e}\n  修复: {settings.get('note', '')}"}
    load_elapsed = time.time() - t0
    print(f"  模型加载: {load_elapsed:.0f}s")

    t0 = time.time()
    try:
        # AutoModel.generate() 不接受固定说话人数。num_speakers 只作校核提示。
        if num_speakers is not None:
            print(f"  提示：预期 {num_speakers} 位说话人；CAM++ 仍自动聚类，须人工核对。")
        generate_kwargs = _build_generate_kwargs(backend_name, language, initial_prompt)
        result = model.generate(input=input_path, **generate_kwargs)
    except Exception as e:
        return {"error": f"FunASR 生成失败: {e}"}
    transcribe_elapsed = time.time() - t0
    print(f"  转写耗时: {transcribe_elapsed:.0f}s")

    if not result:
        return {"error": "FunASR 返回空结果（音频可能无声或不兼容）"}

    # 转 Whisper 兼容 schema
    raw_segments = result[0].get("sentence_info") or []
    if not raw_segments and result[0].get("text"):
        raw_segments = [{"start": 0, "end": 0, "text": result[0]["text"]}]
    if not raw_segments:
        return {"error": "FunASR 结果不含可用文本"}
    segments: list[dict[str, Any]] = []
    for idx, seg in enumerate(raw_segments):
        # SenseVoice 用 'sentence'，paraformer-zh / funasr-nano 用 'text'
        raw_text = seg.get("text") or seg.get("sentence", "")
        # SenseVoice 输出含 special tokens <|yue|><|EMO_xxx|><|Speech|><|woitn|>
        # 统一清理掉，避免污染下游文字稿
        if isinstance(raw_text, str) and "<|" in raw_text:
            raw_text = re.sub(r"<\|[^|]+?\|>", "", raw_text)
        s: dict[str, Any] = {
            "id": idx,
            "start": round(seg["start"] / 1000.0, 2),    # ms -> s
            "end": round(seg["end"] / 1000.0, 2),
            "text": raw_text.strip(),
            # FunASR 无原生字段，下游兼容默认值
            "avg_logprob": -0.3,
            "no_speech_prob": 0.0,
            "compression_ratio": 1.0,
        }
        if diarization_enabled and "spk" in seg:
            s["speaker"] = f"SPEAKER_{seg['spk']}"
        segments.append(s)

    text_join = " ".join(s["text"] for s in segments)
    primary: dict[str, Any] = {
        "text": text_join,
        "segments": segments,
        "language": language,
        "backend": backend_name,
        "load_time_seconds": round(load_elapsed, 1),
        "transcribe_time_seconds": round(transcribe_elapsed, 1),
    }
    write_transcript_json(output_dir, primary)
    if any("speaker" in segment for segment in segments):
        write_transcript_diarized_json(output_dir, dict(primary))

    speakers = {s["speaker"] for s in segments if "speaker" in s}
    print(f"\n✅ FunASR backend={backend_name} 完成: {len(segments)} 段, {len(speakers)} 个说话人")
    return {
        "backend": backend_name,
        "elapsed": transcribe_elapsed,
        "segments_count": len(segments),
        "speakers": sorted(speakers),
        "exit_code": 0,
    }
