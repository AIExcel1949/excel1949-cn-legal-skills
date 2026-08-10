#!/usr/bin/env python3
"""
腾讯云 ASR 转写脚本 — cn-evidence v3.2

调用腾讯云录音文件识别 API，支持说话人分离、批量处理。适合大批量录音或需要最快速度的场景。

调用方式:
    python3 cloud_transcribe.py \
      --input 录音.mp3 \
      --secret-id $TENCENT_SECRET_ID \
      --secret-key $TENCENT_SECRET_KEY \
      --speaker-diarization \
      --speaker-number 2 \
      --output result.json

环境变量（优先级低于命令行参数）:
    TENCENT_SECRET_ID     腾讯云 SecretId
    TENCENT_SECRET_KEY    腾讯云 SecretKey

依赖:
    pip install tencentcloud-sdk-python

===== CHECKPOINT =====
CHECKPOINT 1: 凭证检查
CHECKPOINT 2: 音频文件检查
CHECKPOINT 3: API 调用 + 轮询
CHECKPOINT 4: 结果格式转换
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


# ============================================================
# CHECKPOINT 1: 凭证检查
# ============================================================

def checkpoint_1_credentials(secret_id: str, secret_key: str) -> dict:
    result = {"passed": True, "info": {}}

    if not secret_id:
        print(f"\n❌ CHECKPOINT 1 失败: SecretId 未设置")
        print(f"  💡 设置: export TENCENT_SECRET_ID=your_id")
        print(f"  💡 或传参: --secret-id your_id")
        result["passed"] = False
        return result

    if not secret_key:
        print(f"\n❌ CHECKPOINT 1 失败: SecretKey 未设置")
        print(f"  💡 设置: export TENCENT_SECRET_KEY=your_key")
        result["passed"] = False
        return result

    # 检查 SDK
    try:
        from tencentcloud.common import credential
        from tencentcloud.asr.v20190614 import asr_client, models
        result["info"]["sdk_available"] = True
    except ImportError:
        print(f"\n❌ CHECKPOINT 1 失败: 腾讯云 SDK 未安装")
        print(f"  💡 修复: pip install tencentcloud-sdk-python")
        result["passed"] = False
        return result

    print(f"\n✅ CHECKPOINT 1 通过: 凭证和 SDK 就绪")
    return result


# ============================================================
# CHECKPOINT 2: 音频文件检查
# ============================================================

def checkpoint_2_audio(input_path: str) -> dict:
    result = {"passed": True, "info": {}}

    path = Path(input_path)
    if not path.exists():
        print(f"\n❌ CHECKPOINT 2 失败: 文件不存在: {input_path}")
        result["passed"] = False
        return result

    size_mb = path.stat().st_size / (1024 * 1024)
    result["info"]["file_size_mb"] = round(size_mb, 2)
    result["info"]["file_name"] = path.name

    if size_mb > 512:
        print(f"\n❌ CHECKPOINT 2 失败: 文件过大 ({size_mb:.1f}MB > 512MB)")
        print(f"  💡 腾讯云单文件限制 512MB，请先压缩或分段")
        result["passed"] = False
        return result

    # 检查格式
    suffix = path.suffix.lower()
    supported = {".mp3", ".wav", ".m4a", ".flac", ".pcm", ".ogg", ".aac"}
    if suffix not in supported:
        print(f"\n⚠️  格式 {suffix} 可能不被腾讯云 API 支持")

    print(f"\n✅ CHECKPOINT 2 通过: {path.name} ({size_mb:.1f}MB)")
    return result


# ============================================================
# CHECKPOINT 3+4: API 调用 + 格式转换
# ============================================================

def cloud_transcribe(
    input_path: str,
    secret_id: str,
    secret_key: str,
    speaker_diarization: bool = False,
    speaker_number: int = 0,
    engine_model: str = "16k_zh",
    region: str = "ap-guangzhou",
    output_path: str = "result.json",
) -> int:
    """调用腾讯云 ASR API，轮询结果，转换为标准 JSON。"""

    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.asr.v20190614 import asr_client, models
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

    # 读取并 Base64 编码音频
    print(f"\n📤 上传音频...")
    with open(input_path, "rb") as f:
        audio_base64 = base64.b64encode(f.read()).decode("utf-8")

    # 构建请求
    cred = credential.Credential(secret_id, secret_key)
    httpProfile = HttpProfile()
    httpProfile.endpoint = "asr.tencentcloudapi.com"

    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile

    client = asr_client.AsrClient(cred, region, clientProfile)

    req = models.CreateRecTaskRequest()
    req.EngineModelType = engine_model
    req.ChannelNum = 1
    req.ResTextFormat = 3  # 含时间戳
    req.SourceType = 1      # 1=URL（需上传）, 0=本地上传

    # 说话人分离
    if speaker_diarization:
        req.SpeakerDiarization = 1
        req.SpeakerNumber = speaker_number

    # 先上传获取 URL（简化方案：使用数据长度限制内的直传）
    # 对于大文件，建议使用腾讯云 COS 先上传
    if len(audio_base64) > 3 * 1024 * 1024:  # 超过 3MB Base64
        print(f"\n⚠️  文件较大，API 请求可能超时")
        print(f"  💡 建议先将文件上传至腾讯云 COS 或使用回调方式")

    req.Data = audio_base64
    req.DataLen = len(audio_base64)

    try:
        print(f"\n🚀 发送识别请求...")
        print(f"  引擎: {engine_model}")
        print(f"  说话人分离: {'是 (' + str(speaker_number) + '人)' if speaker_diarization else '否'}")

        resp = client.CreateRecTask(req)
        task_id = resp.Data.TaskId
        print(f"  任务 ID: {task_id}")

    except TencentCloudSDKException as e:
        print(f"\n❌ API 调用失败: {e}")
        return 1

    # 轮询结果
    print(f"\n⏳ 等待识别完成...")
    max_retries = 120  # 最多等 10 分钟
    retry_interval = 5  # 每 5 秒检查一次

    for i in range(max_retries):
        time.sleep(retry_interval)

        try:
            status_req = models.DescribeTaskStatusRequest()
            status_req.TaskId = task_id
            status_resp = client.DescribeTaskStatus(status_req)

            status = status_resp.Data.StatusStr
            print(f"  [{i+1}/{max_retries}] 状态: {status}")

            if status == "success":
                result_text = status_resp.Data.Result
                break
            elif status == "failed":
                print(f"\n❌ 识别失败: {status_resp.Data.ErrorMsg}")
                return 1

        except TencentCloudSDKException as e:
            print(f"\n❌ 查询状态失败: {e}")
            return 1
    else:
        print(f"\n❌ 识别超时（{max_retries * retry_interval}s），请稍后手动查询任务 {task_id}")
        print(f"  查询命令: python3 cloud_transcribe.py --query-task {task_id}")
        return 1

    # 解析结果
    print(f"\n🔧 解析识别结果...")
    try:
        result_json = json.loads(result_text)
    except json.JSONDecodeError:
        # 非 JSON 格式，尝试按文本解析
        result_json = {"text": result_text}

    # 转换为标准格式
    segments = []
    if "Response" in result_json:
        # 新版 API 响应
        data = result_json["Response"].get("Data", result_json["Response"])
    else:
        data = result_json

    # 提取句子级结果
    sentence_list = data.get("ResultDetail", data.get("SentenceList", []))

    if sentence_list:
        for item in sentence_list:
            seg = {
                "start": item.get("StartMs", item.get("start_time", 0)) / 1000,
                "end": item.get("EndMs", item.get("end_time", 0)) / 1000,
                "text": item.get("FinalSentence", item.get("text", "")).strip(),
            }
            # 说话人标签
            if "SpeakerId" in item:
                seg["speaker"] = f"SPEAKER_{item['SpeakerId']}"
            elif speaker_diarization and "speaker" in item:
                seg["speaker"] = f"SPEAKER_{item['speaker']}"

            if seg["text"]:
                segments.append(seg)

    # 如果没有 detail，使用整体文本
    if not segments and data.get("Result"):
        segments = [{"start": 0, "end": 0, "text": data["Result"]}]

    speakers = set(s.get("speaker") for s in segments if "speaker" in s)
    total_duration = segments[-1]["end"] - segments[0]["start"] if segments else 0

    output = {
        "method": "tencent-cloud-asr",
        "engine_model": engine_model,
        "speaker_diarization": speaker_diarization,
        "task_id": task_id,
        "num_segments": len(segments),
        "num_speakers_detected": len(speakers) if speakers else 0,
        "speakers": sorted(speakers) if speakers else [],
        "total_duration_seconds": round(total_duration, 1),
        "segments": segments,
    }

    # 保存
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ CHECKPOINT 3+4 通过")
    if speakers:
        print(f"  检测到 {len(speakers)} 个说话人: {', '.join(sorted(speakers))}")
    print(f"  总段落数: {len(segments)}")
    print(f"  结果保存至: {output_path}")

    return 0


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="腾讯云 ASR 转写 — 云端语音识别 + 说话人分离",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法（无说话人分离）
  python3 cloud_transcribe.py --input 录音.mp3

  # 含说话人分离
  python3 cloud_transcribe.py --input 录音.mp3 --speaker-diarization --speaker-number 2

  # 使用命令行凭证
  python3 cloud_transcribe.py --input 录音.mp3 --secret-id xxx --secret-key yyy
        """,
    )

    parser.add_argument("--input", "-i", required=True, help="输入音频文件路径")
    parser.add_argument("--output", "-o", default="cloud_result.json", help="输出 JSON 路径")
    parser.add_argument("--secret-id", default=os.environ.get("TENCENT_SECRET_ID", ""),
                        help="腾讯云 SecretId（或环境变量 TENCENT_SECRET_ID）")
    parser.add_argument("--secret-key", default=os.environ.get("TENCENT_SECRET_KEY", ""),
                        help="腾讯云 SecretKey（或环境变量 TENCENT_SECRET_KEY）")
    parser.add_argument("--speaker-diarization", action="store_true",
                        help="开启说话人分离")
    parser.add_argument("--speaker-number", type=int, default=0,
                        help="说话人数（0=自动推断，建议 2）")
    parser.add_argument("--engine-model", default="16k_zh",
                        choices=["16k_zh", "8k_zh", "16k_en", "8k_en", "16k_ca", "16k_zh_large"],
                        help="识别引擎（默认 16k_zh 中文通用）")
    parser.add_argument("--region", default="ap-guangzhou",
                        help="API 区域（默认 ap-guangzhou）")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  cn-evidence v3.2 — 腾讯云 ASR")
    print(f"{'='*60}")

    # CHECKPOINT 1
    cp1 = checkpoint_1_credentials(args.secret_id, args.secret_key)
    if not cp1["passed"]:
        sys.exit(1)

    # CHECKPOINT 2
    cp2 = checkpoint_2_audio(args.input)
    if not cp2["passed"]:
        sys.exit(1)

    # 执行
    ret = cloud_transcribe(
        input_path=args.input,
        secret_id=args.secret_id,
        secret_key=args.secret_key,
        speaker_diarization=args.speaker_diarization,
        speaker_number=args.speaker_number,
        engine_model=args.engine_model,
        region=args.region,
        output_path=args.output,
    )

    print(f"{'='*60}\n")
    sys.exit(ret)


if __name__ == "__main__":
    main()
