#!/usr/bin/env python3
"""
说话人分离脚本 — cn-evidence v3.2

支持 3 种方法：
  - funasr（默认）：FunASR Paraformer + CAM++，一站式 ASR + 说话人分离，ModelScope 模型
  - sherpa-onnx：仅说话人分离（不转写），ONNX Runtime 推理，模型 ~47MB
  - whisperx：whisperX + pyannote，走 hf-mirror，跨境律师适用

调用方式:
    # 默认 FunASR
    python3 diarize.py --input 录音.wav --num-speakers 2

    # sherpa-onnx 模式
    python3 diarize.py --input 录音.wav --method sherpa-onnx --num-speakers 2

    # whisperX 模式（需先 export HF_ENDPOINT=https://hf-mirror.com）
    python3 diarize.py --input 录音.wav --method whisperx --num-speakers 2

    # 同时输出转写文本（仅 funasr 模式）
    python3 diarize.py --input 录音.wav --transcribe --output result.json

===== 反例 =====
反例 1: 不安装依赖就想跑
    错误! 先运行: bash scripts/install.sh
反例 2: 采样率不匹配直接送入模型
    错误! 必须 16kHz 单声道，脚本会自动用 librosa/ffmpeg 转换
反例 3: 单说话人录音强制指定 --num-speakers 2
    错误! 会导致说话人识别错误。不确定人数时不传 --num-speakers 让模型自动推断
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


# ============================================================
# CHECKPOINT 1: 环境检查
# ============================================================

def checkpoint_1_environment(method: str) -> dict:
    """检查对应方法的环境是否就绪。"""
    result = {"passed": True, "warnings": [], "info": {}}

    if method == "funasr":
        try:
            import funasr
            result["info"]["funasr_version"] = funasr.__version__
            print(f"\n✅ CHECKPOINT 1 通过: FunASR {funasr.__version__} 可用")
        except ImportError:
            print(f"\n❌ CHECKPOINT 1 失败: FunASR 未安装")
            print(f"  💡 修复: pip install funasr torch torchaudio")
            print(f"  💡 或运行: bash scripts/install.sh")
            result["passed"] = False

    elif method == "sherpa-onnx":
        try:
            import sherpa_onnx
            result["info"]["sherpa_onnx_available"] = True
            print(f"\n✅ CHECKPOINT 1 通过: sherpa-onnx 可用")
        except ImportError:
            print(f"\n❌ CHECKPOINT 1 失败: sherpa-onnx 未安装")
            print(f"  💡 修复: pip install sherpa-onnx")
            result["passed"] = False

    elif method == "whisperx":
        # 检查 HF_ENDPOINT
        hf_endpoint = os.environ.get("HF_ENDPOINT", "")
        if hf_endpoint:
            print(f"\n✅ HF_ENDPOINT 已设置: {hf_endpoint}")
        else:
            print(f"\n⚠️  未设置 HF_ENDPOINT，可能无法下载模型")
            print(f"  💡 国内建议: export HF_ENDPOINT=https://hf-mirror.com")
            print(f"  💡 海外可直接使用: export HF_ENDPOINT=https://huggingface.co")
            result["warnings"].append("HF_ENDPOINT 未设置，建议设为 https://hf-mirror.com（国内）或 https://huggingface.co（海外）")

        try:
            import whisperx
            result["info"]["whisperx_available"] = True
            print(f"✅ CHECKPOINT 1 通过: whisperX 可用")
        except ImportError:
            print(f"\n❌ CHECKPOINT 1 失败: whisperX 未安装")
            print(f"  💡 修复: export HF_ENDPOINT=https://hf-mirror.com && pip install whisperx")
            result["passed"] = False

    return result


# ============================================================
# CHECKPOINT 2: 音频文件检查
# ============================================================

def checkpoint_2_audio(input_path: str) -> dict:
    """检查音频文件存在性和采样率。"""
    result = {"passed": True, "warnings": [], "info": {}}

    path = Path(input_path)
    if not path.exists():
        print(f"\n❌ CHECKPOINT 2 失败: 文件不存在: {input_path}")
        result["passed"] = False
        return result

    result["info"]["file_path"] = str(path.absolute())
    result["info"]["file_size_mb"] = round(path.stat().st_size / (1024 * 1024), 2)

    # 获取采样率
    try:
        import shutil
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            r = subprocess.run(
                [ffprobe, "-v", "quiet", "-show_entries", "stream=sample_rate,channels",
                 "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split(",")
                if len(parts) >= 2:
                    result["info"]["sample_rate"] = int(parts[0])
                    result["info"]["channels"] = int(parts[1])
    except Exception:
        pass

    sr = result["info"].get("sample_rate")
    if sr and sr != 16000:
        print(f"\n⚠️  采样率 {sr}Hz，将自动转换为 16kHz")
        result["warnings"].append(f"采样率 {sr}Hz != 16000Hz，将自动转换")

    print(f"\n✅ CHECKPOINT 2 通过: {path.name} ({result['info']['file_size_mb']} MB)")
    if sr:
        print(f"  采样率: {sr}Hz, 声道: {result['info'].get('channels', '?')}")

    return result


# ============================================================
# 音频预处理：统一转为 16kHz 单声道 WAV
# ============================================================

def preprocess_audio(input_path: str, output_dir: Path) -> str:
    """将音频转为 16kHz 单声道 WAV，返回处理后文件路径。"""
    output_path = output_dir / "audio_16k.wav"

    try:
        import librosa
        import soundfile as sf
        import numpy as np

        audio, sr = librosa.load(input_path, sr=16000, mono=True)
        sf.write(str(output_path), audio, 16000)
        print(f"\n🔧 音频预处理完成: {output_path} (16kHz 单声道, {len(audio)/sr:.1f}s)")
        return str(output_path)

    except ImportError:
        pass

    # 回退到 ffmpeg
    try:
        import shutil
        if shutil.which("ffmpeg"):
            subprocess.run(
                ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1",
                 str(output_path)],
                capture_output=True, check=True
            )
            print(f"\n🔧 ffmpeg 预处理完成: {output_path}")
            return str(output_path)
    except Exception:
        pass

    # 无法转换，直接返回原文件
    print(f"\n⚠️  无法预处理音频，将直接使用原文件")
    return input_path


# ============================================================
# 方法一: FunASR
# ============================================================

def diarize_funasr(input_path: str, num_speakers: int | None, transcribe: bool, output_path: str) -> dict:
    """FunASR Paraformer + CAM++ 一站式 ASR + 说话人分离。"""
    print(f"\n🎤 使用 FunASR CAM++ 进行 ASR + 说话人分离...")

    try:
        from funasr import AutoModel
    except ImportError:
        return {"error": "FunASR 未安装。运行: pip install funasr torch torchaudio"}

    model_kwargs = {
        "model": "paraformer-zh",
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
        "spk_model": "cam++",
    }

    print(f"  模型: Paraformer-zh + FSMN-VAD + CT-PUNC + CAM++")
    print(f"  正在加载模型（首次运行从 ModelScope 下载，约 300MB）...")

    t0 = time.time()
    try:
        model = AutoModel(**model_kwargs)
    except Exception as e:
        return {"error": f"模型加载失败: {e}。检查网络连接或 pip install funasr --upgrade"}

    load_time = time.time() - t0
    print(f"  模型加载耗时: {load_time:.0f}s")

    print(f"  正在转写（含说话人分离）...")
    t0 = time.time()
    try:
        # NOTE: num_speakers 参数被接收但 FunASR generate() 不直接支持指定说话人数。
        # CAM++ 说话人分离通过聚类算法自动推断说话人数量，无法通过 generate() 参数直接指定。
        result = model.generate(input=input_path)
    except Exception as e:
        return {"error": f"转写失败: {e}"}

    transcribe_time = time.time() - t0
    print(f"  转写耗时: {transcribe_time:.0f}s")

    if not result or not result[0].get("sentence_info"):
        return {"error": "转写结果为空，可能音频无声或格式不兼容"}

    # 提取结果
    segments = []
    for seg in result[0]["sentence_info"]:
        segments.append({
            "speaker": f"SPEAKER_{seg.get('spk', 0)}",
            "start": seg["start"] / 1000,   # ms → s
            "end": seg["end"] / 1000,
            "text": seg["text"].strip(),
        })

    # 统计
    speakers = set(s["speaker"] for s in segments)
    total_duration = segments[-1]["end"] - segments[0]["start"] if segments else 0

    summary = {
        "method": "funasr",
        "model": "paraformer-zh + CAM++",
        "num_segments": len(segments),
        "num_speakers_detected": len(speakers),
        "speakers": sorted(speakers),
        "total_duration_seconds": round(total_duration, 1),
        "load_time_seconds": round(load_time, 1),
        "transcribe_time_seconds": round(transcribe_time, 1),
        "segments": segments,
    }

    print(f"\n✅ 说话人分离完成:")
    print(f"  检测到 {len(speakers)} 个说话人: {', '.join(sorted(speakers))}")
    print(f"  总段落数: {len(segments)}")
    print(f"  总时长: {total_duration:.1f}s")

    return summary


# ============================================================
# 方法二: sherpa-onnx
# ============================================================

def diarize_sherpa_onnx(input_path: str, num_speakers: int | None) -> dict:
    """sherpa-onnx 说话人分离（仅分离，不含 ASR）。"""
    print(f"\n🔊 使用 sherpa-onnx 进行说话人分离（仅分离，不含转写）...")

    try:
        import sherpa_onnx
        import soundfile as sf
    except ImportError:
        return {"error": "sherpa-onnx 未安装。运行: pip install sherpa-onnx soundfile librosa"}

    # 模型路径
    cache_dir = Path.home() / ".cache" / "sherpa-onnx"
    seg_model = cache_dir / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    emb_model = cache_dir / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"

    # 检查并下载模型
    if not seg_model.exists() or not emb_model.exists():
        print(f"  模型未缓存，正在下载 (~47MB)...")
        cache_dir.mkdir(parents=True, exist_ok=True)
        _download_sherpa_models(cache_dir, seg_model, emb_model)

    # 加载音频
    print(f"  加载音频: {input_path}")
    audio, sr = sf.read(input_path)
    if sr != 16000:
        try:
            import librosa
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
            sr = 16000
        except ImportError:
            return {"error": "需要 librosa 进行采样率转换: pip install librosa"}
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)  # 转单声道

    # 配置
    num_clusters = num_speakers if num_speakers else -1
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(seg_model)
            ),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(emb_model)
        ),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_clusters,
            threshold=0.5
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )

    print(f"  正在分离（说话人数: {'自动推断' if num_speakers is None else num_speakers}）...")
    t0 = time.time()

    try:
        sd = sherpa_onnx.OfflineSpeakerDiarization(config)
        result = sd.process(audio, sr).sort_by_start_time()
    except Exception as e:
        return {"error": f"sherpa-onnx 处理失败: {e}"}

    elapsed = time.time() - t0

    segments = []
    for seg in result:
        segments.append({
            "speaker": f"SPEAKER_{seg.speaker}",
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": "",  # 无转写，需后续合并
        })

    speakers = set(s["speaker"] for s in segments)

    summary = {
        "method": "sherpa-onnx",
        "model": "pyannote-segmentation-3-0 + 3D-Speaker eres2net (zh)",
        "num_segments": len(segments),
        "num_speakers_detected": len(speakers),
        "speakers": sorted(speakers),
        "total_duration_seconds": round(segments[-1]["end"] - segments[0]["start"], 1) if segments else 0,
        "process_time_seconds": round(elapsed, 1),
        "segments": segments,
    }

    print(f"\n✅ 说话人分离完成:")
    print(f"  检测到 {len(speakers)} 个说话人")
    print(f"  总段落数: {len(segments)}")
    print(f"  耗时: {elapsed:.0f}s")

    return summary


def _download_sherpa_models(cache_dir: Path, seg_model: Path, emb_model: Path):
    """下载 sherpa-onnx 模型（~47MB）。"""
    import urllib.request
    import tarfile
    import tempfile

    SEG_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
    EMB_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"

    if not emb_model.exists():
        print(f"  下载嵌入模型 (40MB)...")
        urllib.request.urlretrieve(EMB_URL, str(emb_model))

    if not seg_model.exists():
        print(f"  下载分割模型 (7MB)...")
        with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as tmp:
            urllib.request.urlretrieve(SEG_URL, tmp.name)
            with tarfile.open(tmp.name, "r:bz2") as tar:
                tar.extractall(path=str(cache_dir))
            os.unlink(tmp.name)


# ============================================================
# 方法三: whisperX
# ============================================================

def diarize_whisperx(input_path: str, num_speakers: int | None, transcribe: bool) -> dict:
    """whisperX + pyannote，走 hf-mirror。"""
    print(f"\n🌐 使用 whisperX 进行 ASR + 说话人分离...")

    # 确保 HF_ENDPOINT
    if "HF_ENDPOINT" not in os.environ:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        print(f"  已自动设置 HF_ENDPOINT=https://hf-mirror.com")

    try:
        import whisperx
        import gc
    except ImportError:
        return {"error": "whisperX 未安装。运行: export HF_ENDPOINT=https://hf-mirror.com && pip install whisperx"}

    device = "cpu"
    model_name = "medium"
    batch_size = 8

    try:
        # 1. 加载模型
        print(f"  加载 Whisper 模型: {model_name}...")
        t0 = time.time()
        model = whisperx.load_model(model_name, device, compute_type="float32")
        load_time = time.time() - t0

        # 2. 转写
        print(f"  转写中...")
        t0 = time.time()
        audio = whisperx.load_audio(input_path)
        result = model.transcribe(audio, batch_size=batch_size, language="zh")
        transcribe_time = time.time() - t0

        # 3. 对齐（whisperX 的 wav2vec2 对齐主要支持英文，中文跳过）
        # result = whisperx.align(result["segments"], model_a, metadata, audio, device)

        # 4. 说话人分离
        print(f"  说话人分离中...")
        t0 = time.time()

        # 使用 hf-mirror 加载 pyannote
        diarize_model = whisperx.DiarizationPipeline(
            model_name="pyannote/speaker-diarization-3.1",
            device=device,
        )
        diarize_segments = diarize_model(audio)

        # 合并
        result = whisperx.assign_word_speakers(diarize_segments, result)
        diarize_time = time.time() - t0

        segments = []
        for seg in result["segments"]:
            speaker = seg.get("speaker", "SPEAKER_0")
            if isinstance(speaker, (int, float)):
                speaker = f"SPEAKER_{int(speaker)}"
            elif not str(speaker).startswith("SPEAKER_"):
                speaker = f"SPEAKER_{speaker}"

            segments.append({
                "speaker": str(speaker),
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "text": seg.get("text", "").strip(),
            })

        speakers = set(s["speaker"] for s in segments)

        summary = {
            "method": "whisperx",
            "model": f"Whisper {model_name} + pyannote/speaker-diarization-3.1",
            "num_segments": len(segments),
            "num_speakers_detected": len(speakers),
            "speakers": sorted(speakers),
            "total_duration_seconds": round(segments[-1]["end"] - segments[0]["start"], 1) if segments else 0,
            "load_time_seconds": round(load_time, 1),
            "transcribe_time_seconds": round(transcribe_time, 1),
            "diarize_time_seconds": round(diarize_time, 1),
            "segments": segments,
        }

        print(f"\n✅ whisperX 完成:")
        print(f"  检测到 {len(speakers)} 个说话人")
        print(f"  总段落数: {len(segments)}")
        print(f"  加载: {load_time:.0f}s, 转写: {transcribe_time:.0f}s, 分离: {diarize_time:.0f}s")

        gc.collect()
        return summary

    except Exception as e:
        return {"error": f"whisperX 处理失败: {e}"}


# ============================================================
# CHECKPOINT 3: 结果验证
# ============================================================

def checkpoint_3_result(summary: dict) -> dict:
    """验证输出结果合理性。"""
    result = {"passed": True, "warnings": []}

    if "error" in summary:
        print(f"\n❌ CHECKPOINT 3 失败: {summary['error']}")
        result["passed"] = False
        return result

    segments = summary.get("segments", [])
    num_speakers = summary.get("num_speakers_detected", 0)
    num_segments = len(segments)

    if num_segments == 0:
        print(f"\n❌ CHECKPOINT 3 失败: 0 个段落（可能音频无声）")
        result["passed"] = False
        return result

    if num_speakers == 0:
        print(f"\n❌ CHECKPOINT 3 失败: 未检测到说话人")
        result["passed"] = False
        return result

    if num_speakers == 1:
        print(f"\n⚠️  CHECKPOINT 3 警告: 仅检测到 1 个说话人（可能是单人录音或分离不准）")
        result["warnings"].append("仅检测到1个说话人")

    if num_segments < 3 and summary.get("total_duration_seconds", 0) > 60:
        print(f"\n⚠️  CHECKPOINT 3 警告: 长录音仅 {num_segments} 段（可能遗漏）")
        result["warnings"].append("段落数异常少")

    print(f"\n✅ CHECKPOINT 3 通过: {num_segments} 段, {num_speakers} 个说话人")
    return result


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="说话人分离 — 支持 FunASR / sherpa-onnx / whisperX 三种方法",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 默认 FunASR（推荐）
  python3 diarize.py --input 录音.wav --num-speakers 2

  # sherpa-onnx（轻量备选）
  python3 diarize.py --input 录音.wav --method sherpa-onnx --num-speakers 2

  # whisperX（跨境律师，需 export HF_ENDPOINT）
  python3 diarize.py --input 录音.wav --method whisperx --num-speakers 2
        """,
    )

    parser.add_argument("--input", "-i", required=True, help="输入音频文件路径")
    parser.add_argument("--output", "-o", default="diarization.json", help="输出 JSON 文件路径")
    parser.add_argument("--method", "-m", default="funasr",
                        choices=["funasr", "sherpa-onnx", "whisperx"],
                        help="说话人分离方法（默认: funasr）")
    parser.add_argument("--num-speakers", "-n", type=int, default=None,
                        help="指定说话人数（默认自动推断）")
    parser.add_argument("--transcribe", action="store_true",
                        help="同时输出转写文本（仅 funasr/whisperx 模式支持）")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  cn-evidence v3.2 — 说话人分离")
    print(f"  方法: {args.method}")
    print(f"{'='*60}")

    # CHECKPOINT 1
    cp1 = checkpoint_1_environment(args.method)
    if not cp1["passed"]:
        sys.exit(1)

    # CHECKPOINT 2
    cp2 = checkpoint_2_audio(args.input)
    if not cp2["passed"]:
        sys.exit(1)

    # 预处理音频
    output_dir = Path(args.output).parent or Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_path = args.input
    if cp2["info"].get("sample_rate") and cp2["info"]["sample_rate"] != 16000:
        audio_path = preprocess_audio(args.input, output_dir)

    # 执行分离
    if args.method == "funasr":
        summary = diarize_funasr(audio_path, args.num_speakers, args.transcribe, args.output)
    elif args.method == "sherpa-onnx":
        summary = diarize_sherpa_onnx(audio_path, args.num_speakers)
    elif args.method == "whisperx":
        summary = diarize_whisperx(audio_path, args.num_speakers, args.transcribe)

    # CHECKPOINT 3
    cp3 = checkpoint_3_result(summary)
    if not cp3["passed"]:
        sys.exit(1)

    # 保存结果
    output_data = {k: v for k, v in summary.items() if k != "segments"}
    output_data["segments"] = summary.get("segments", [])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n📁 结果已保存: {args.output}")
    print(f"{'='*60}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
