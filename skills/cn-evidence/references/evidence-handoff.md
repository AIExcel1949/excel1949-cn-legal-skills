# 统一证据数据层交接

## 目的

`export_evidence_record.py` 把转写中间数据转换为 `cn-legal-core` 可读取的来源记录和证据记录。它只建立可追踪关系，不自动填写证明目的、待证事实，也不对真实性、合法性、关联性作结论。

## 使用

```bash
.venv/bin/python skills/cn-evidence/scripts/export_evidence_record.py \
  转写结果.json \
  --matter-id MAT-001 \
  --source-id SRC-AUDIO-001 \
  --evidence-id EVD-AUDIO-001 \
  --evidence-name 催收电话录音 \
  --audio-file 原始录音.mp3 \
  --output evidence-handoff.json
```

未提供 `--audio-file` 时仍可生成交接文件，但会保留 `original_audio_not_rechecked` 阻断项。哈希不一致、未完成逐句回听或存在低置信度段时同样阻断后续定稿。

## 边界

- `review.status` 仅表示文字稿是否逐句回听，不等于证据三性已经核验。
- `fact_ids` 固定为空数组，必须由 `cn-evidence-map` 结合事实台账后人工建立。
- 无原始哈希时使用全零占位以保持数据结构可验证，同时生成阻断项；不得把该占位视为真实哈希。
- 输出固定为 `lawyer_review_required`，不得通过命令行直接升级为已核验状态。
