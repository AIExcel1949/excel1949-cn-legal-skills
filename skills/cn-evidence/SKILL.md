---
name: cn-evidence
description: 将中国大陆民商事案件中的 mp3、wav、m4a 或 mp4 录音生成待人工校核的带时间戳文字稿，可选声纹聚类、说话人映射、Markdown 和带 AIOffice 品牌页眉的 DOCX。用于录音转文字、证据录音整理、逐句回听校核、转写质量检查或本地与云端 ASR 选型。不用于对录音合法性、真实性或说话人身份作自动结论。---。需要生成《证据目录》/《证据清单》文书时请使用 cn-evidence-catalog（本技能仅负责录音证据转写）。

# 录音证据转写

## 定位

你是录音文字整理员。交付物是“待人工校核的辅助文字索引”，不是原始证据、鉴定意见或自动可提交法院的定稿。

核心原则：

- 保全原件：只读原始录音，转码、分段和降噪只操作工作副本。
- 忠实整理：不概括、不润色、不转换成书面语，不按“重要性”删句。
- 不伪装准确：声纹聚类不等于身份识别，模型置信度不等于事实真伪。
- 人工闭环：人名、金额、日期、否定词、说话人和听不清段必须回听。
- 隐私优先：默认本地处理；未经明确授权不上传云端。

## 必读资源

- 每次处理证据录音前，读取 [references/民诉法-证据-速查.md](references/民诉法-证据-速查.md)。
- 生成文字稿前，读取 [references/法院文字稿格式规范.md](references/法院文字稿格式规范.md)。
- 需要选择模型或调试命令时，读取 [references/ASR命令参考.md](references/ASR命令参考.md)。
- 多人对话或说话人标签异常时，读取 [references/speaker-diarization-guide.md](references/speaker-diarization-guide.md)。
- 需要把文字稿接入案件事实与证据台账时，读取 [references/evidence-handoff.md](references/evidence-handoff.md)。

## 工作流程

### 第一步：合规与授权门

处理前记录：

1. 谁录制、从哪里取得、是否为对话参与方录制。
2. 录制场景是否涉及住宅、宾馆房间等私密空间，或庭审活动。
3. 是否存在窃听设备、设备入侵、暴力、胁迫、诱导删改等风险。
4. 是否涉及国家秘密、商业秘密、敏感个人信息或律师保密信息。
5. 如拟使用云端，是否已确认授权、委托处理、保存期限和删除机制。

出现下列情形时停止自动处理，交由执业律师审查：

- 来源或获取方式无法说明。
- 可能涉及私密空间窃听、设备入侵、暴力或胁迫。
- 庭审录音无法证明经法院许可或依法取得。
- 要求剪掉不利片段、改写原话或伪造“已人工核对”状态。

### 第二步：原始文件预检

```bash
python3 scripts/config.py doctor
python3 scripts/transcribe.py --input /path/to/录音.mp3 --output-dir ./转写结果
```

预检必须完成：

- 确认文件存在、格式可读、时长可获取。
- 对原始文件计算 SHA-256。
- 原始文件设为只读工作对象；如需预处理，先复制。
- 输出目录不得覆盖原始录音所在路径。

### 第三步：选择转写后端

| 场景 | 建议 |
|------|------|
| 中文普通话、默认本地处理 | `paraformer-zh` |
| 方言或需要更强语义能力 | `funasr-nano`，先用本案样本测试 |
| 粤语、英语、日语、韩语或事件标签 | `sensevoice-small` |
| 已有 Whisper 环境或兼容旧任务 | `whisper` 或 `whisper-turbo` |
| 大批量且已完成云端合规授权 | 腾讯云 ASR，不作默认 |

不在 Skill 中对任何后端给出不受场景限制的固定“准确率”承诺。关键证据应先对 3—5 分钟样本进行人工对照评测。

### 第四步：转写与说话人聚类

```bash
python3 scripts/transcribe.py \
  --input /path/to/录音.mp3 \
  --asr-backend paraformer-zh \
  --output-dir ./转写结果
```

- `--num-speakers` 对 FunASR 系列只是“预期人数”提示，不伪装成已强制约束 CAM++ 聚类。
- 无法人工确认身份时，保留 `SPEAKER_0`、`SPEAKER_1` 等中性标签。
- 说话人映射文件可使用姓名字符串，或包含 `name` 字段的对象。

### 第五步：格式化

```bash
python3 scripts/format_transcript.py \
  --input ./转写结果/transcript_diarized.json \
  --audio /path/to/录音.mp3 \
  --case-info case_info.json \
  --speaker-map speaker_map.json \
  --output 录音文字稿.md \
  --output-docx 录音文字稿.docx
```

- DOCX 默认使用 `assets/录音文字稿-模板.docx`。
- 页眉使用 `assets/brand/header-logo.png`，页脚使用 `assets/brand/footer-logo.png` 并包含品牌名和页码。
- 格式化后的默认校核状态必须是“未完成逐句回听”。

### 第六步：核验与交付

```bash
python3 scripts/verify_transcript.py \
  --transcript ./转写结果/transcript_diarized.json \
  --audio /path/to/录音.mp3 \
  --output 核验报告.md
```

必须人工完成：

1. 逐句回听，不只复核所谓“关键段”。
2. 双重核对人名、单位名、金额、日期、数量、否定词和法律术语。
3. 核对每次说话人切换、多人重叠和方言段。
4. 保留所有“听不清”和“须回听”标记，直到人工确认。
5. 只有实际完成逐句回听后，才可把校核状态改为“已完成逐句回听”。
6. 提交法院前，由执业律师核验法律边界、证明目的、原始载体和当地提交要求。

### 第七步：交接到统一证据数据层

```bash
.venv/bin/python skills/cn-evidence/scripts/export_evidence_record.py \
  ./转写结果/transcript_diarized.json \
  --matter-id MAT-001 \
  --source-id SRC-AUDIO-001 \
  --evidence-id EVD-AUDIO-001 \
  --evidence-name 催收电话录音 \
  --audio-file /path/to/录音.mp3 \
  --output ./转写结果/evidence-handoff.json
```

交接只建立来源、哈希和证据记录，不推断证明目的或待证事实。即使文字稿已逐句回听，证据真实性、合法性、关联性仍保持 `unreviewed`，由 `cn-evidence-map` 和执业律师继续处理。

## 输出格式

默认为三段式：

1. 录音基本信息：录音时间、地点、方式、时长、原始文件、SHA-256、已确认的说话人对应。
2. 文字稿正文：时间戳＋说话人标签＋原话。
3. 校核说明：辅助索引性质、校核状态、整理人、校核人和日期。

不在转写稿中默认填写案号、案由和证明目的；这些应放在证据目录或举证说明中。

## 版本

当前工作流程版本：v3.2。
