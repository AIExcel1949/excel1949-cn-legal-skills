# 输入契约与复核方法

## 原始来源

`sources` 中每条记录都必须包含：

- `source_id`：本次工作簿内的稳定编号；
- `source_kind`：合同、制度、工资记录、沟通记录、社保记录、证言或其他；
- `source_locator`：文件名、页码、段落、系统导出位置或 URL；
- `original_text`：未改写的原文或经确认的原文摘录；
- `sha256`：`original_text` 以 UTF-8 编码后的 SHA-256；
- `verification_status`：`unverified`、`source_checked` 或 `lawyer_verified`；
- `verified_on`：核验日期，未核验时为 `null`。

脚本不会修正原文。发现 OCR 错误、截断或冲突时，另建来源记录并保留两个版本。

## 劳动关系候选

`relationship_review.candidate_types` 是律师希望比较的类型。`signals` 中的每个观察必须引用来源，可同时支持多个候选。脚本只计数，不加权、不排名、不选择“真实关系”。

## 全周期审查

`lifecycle_reviews` 的 `category` 使用 SKILL.md 列明的八类枚举。每个审查事项包含：

- 中立问题 `question`；
- 事实来源 `fact_source_ids`；
- 官方法源候选 `authority_ids`；
- 待研究或待取证事项 `open_questions`；
- 固定为非结论性的 `review_state`。

`proposed_actions` 只是待复核任务。`adverse_effect_candidate: true` 表示它可能对劳动者产生不利影响，脚本必须将其送入人工决策队列，不代表该行动可行。

## 地方化

国家层面法源不能替代用工地的工资、病假、医疗期、婚产假、社保缴费、仲裁管辖等地方规则。未加载并核验地方依据时，必须在报告中保留缺口。
