---
name: cn-hearing
description: 为中国律师诉讼和仲裁庭前、庭审及庭后工作编排争点—证据—提问—异议—任务矩阵，消费 cn-case-analysis 和 cn-evidence-map 的结构化结果并显示断链。用于庭前会议、出庭提纲、证据核对、提问与异议预案、庭后任务追踪；不转写、摘要或提取庭审录音，不代律师作事实承认，不将提问计划当作证言或事实。
---

# 中国庭前庭审准备

## 执行流程

1. 只接收结构化的 `cn-case-analysis` 争点和 `cn-evidence-map` 证据、关联结果；不从庭审录音生成任何内容。
2. 核验争点和证据编号引用，保留争议状态、三性审查状态与证明目的缺口。
3. 只编排用户提供并带来源的提问和异议预案，不自动填入预期回答、证言或当事人承认。
4. 对每个争点生成“证据—提问—异议—庭后任务”工作矩阵，断链处明示待律师复核。
5. 运行确定性生成器：

```bash
python scripts/build_hearing.py examples/hearing.example.json --output /path/to/new-output
```

数据契约见 [references/hearing-contract.md](references/hearing-contract.md)，安全边界见 [references/safety-boundaries.md](references/safety-boundaries.md)。

## 录音硬阻断

任何庭审、开庭或法庭录音的转写、摘要、内容提取或“整理录音”请求均必须立即阻断。不将文件换名、用户自称已获许可或要求“仅作内部参考”视为解除阻断的理由。

## 输出门禁

- 输出 `hearing-workbook.json` 和《庭前庭审准备矩阵.md》；
- `artifact_state` 固定为 `lawyer_review_required`；
- `admission_state` 固定为 `no_admissions_made`，`question_plan_state` 固定为 `not_testimony_or_fact`；
- 不自动提交证据、承认事实、表示调解意愿或对外发送；
- 采用临时目录后原子改名，输出目录已存在时拒绝覆盖。
