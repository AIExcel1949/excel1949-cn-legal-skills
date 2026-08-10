# ASR 命令参考（v3.2）

> 只在需要选择后端或排查转写问题时读取。不得把公开基准中的错误率直接当作本案录音的准确率。关键证据应先抽取 3—5 分钟代表性片段，与人工真值对照后再选后端。

## 一、统一入口

```bash
python3 scripts/config.py doctor

python3 scripts/transcribe.py \
  --input /path/to/录音.mp3 \
  --asr-backend paraformer-zh \
  --language zh \
  --output-dir ./转写结果
```

可用本地后端：

- `paraformer-zh`
- `funasr-nano`
- `sensevoice-small`
- `whisper`
- `whisper-turbo`

云端腾讯 ASR 使用独立脚本，只有完成授权和安全审查后才可启用。

## 二、后端选择

| 后端 | 适合场景 | 主要限制 |
|------|---------|---------|
| `paraformer-zh` | 中文普通话、本地默认 | 方言、重叠语音和远场效果需以样本测试 |
| `funasr-nano` | 中文方言、口音、需热词的任务 | 资源占用较高；当前说话人分离能力依赖新版 FunASR 和配套模型 |
| `sensevoice-small` | 中文、粤语、英语、日语、韩语及事件标签 | 事件标签不等于法律意义上的情绪判断；说话人标签仍需人工确认 |
| `whisper` | 兼容既有 Whisper 流程、纯本地 | 中文专名、金额和日期必须重点回听 |
| `whisper-turbo` | 已有 Whisper 环境、希望平衡速度与资源 | 仍需用本案样本评估，不作固定准确率承诺 |

## 三、直接调用

### Paraformer-zh

```bash
python3 scripts/asr_paraformer.py \
  --input 录音.mp3 \
  --language zh \
  --output-dir ./转写结果
```

### Fun-ASR-Nano

```bash
python3 scripts/asr_funasr_nano.py \
  --input 录音.mp3 \
  --language zh \
  --initial-prompt 借款，还款，本金，利息 \
  --output-dir ./转写结果
```

Fun-ASR-Nano 的热词在 `model.generate` 阶段通过 `hotwords` 传入，不能错误地放入 `AutoModel` 构造参数。启用说话人分离时需 `vad_model`、`spk_model` 和 `punc_model` 配合。

官方实现与参数以 [Fun-ASR 仓库](https://github.com/FunAudioLLM/Fun-ASR) 和 [FunASR 教程](https://github.com/modelscope/FunASR/blob/main/docs/tutorial/README.md) 为准。

### SenseVoice-Small

```bash
python3 scripts/asr_sensevoice.py \
  --input 录音.mp3 \
  --language yue \
  --output-dir ./转写结果
```

语言可选 `zh`、`yue`、`en`、`ja`、`ko` 或 `auto`。输出中的语言、情感和事件 token 由脚本清理，不得未经人工复核写成事实判断。

### Whisper

```bash
python3 scripts/asr_whisper.py \
  --input 录音.mp3 \
  --whisper-model large-v3 \
  --language zh \
  --output-dir ./转写结果
```

### Whisper Turbo

```bash
python3 scripts/asr_whisper_turbo.py \
  --input 录音.mp3 \
  --language zh \
  --output-dir ./转写结果
```

## 四、热词

- 热词只帮助识别，不证明该词实际出现。
- 仅加入与案件已有材料能够印证的姓名、单位名、专有名词和法律术语。
- 不把预期结论、争议事实或完整答案写进热词。
- 转写后仍须回听热词命中位置，防止模型因提示而误写。

## 五、长录音

- 超过 1 小时可先对工作副本分段；原始文件不得分段覆盖。
- 分段必须保存累计时间偏移，合并时恢复为相对原始录音的时间戳。
- 不使用有损降噪或自动静音删除生成“新原件”。
- 发生中断时保留已完成分段及日志，避免重复覆盖。

## 六、输出文件

- `transcript.json`：统一转写结果。
- `transcript_diarized.json`：只有确实生成说话人聚类标签时才输出。
- `transcribe.log`：记录后端、参数、输入文件 SHA-256 和运行信息。
- `文字稿.md`、`文字稿.docx`：由 `format_transcript.py` 生成。

## 七、质量判断

不得用一个固定百分比替代质量评估。至少检查：

1. 字符或词错误率；
2. 人名、单位名、金额、日期、数量和否定词的专项错误；
3. 说话人切换错误；
4. 漏句、重复、幻听和非语音误识别；
5. 方言、重叠语音、远场和噪声段；
6. 关键时间戳能否快速定位到原始录音。

任何自动评分都不能替代逐句回听。

