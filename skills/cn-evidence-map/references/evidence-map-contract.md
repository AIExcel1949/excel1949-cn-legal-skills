# 证据映射数据契约

## 共享实体

sources、facts、issues、claims 和 evidence 分别引用 cn-legal-core 的 source、fact-ledger、issue、claim 和 evidence Schema。编号必须稳定且唯一，跨 Skill 传递时不改号。

defenses 是抗辩原文记录，必须保留来源定位。“对诉请不予认可”不能替代当事人实际陈述。

## 三类关系

1. evidence_fact_links：证据与待证事实。proof_purpose 可选，但一旦填写，只能为 source_stated 或 human_confirmed，且必须同时记录原文定位或用户确认说明。
2. fact_issue_links：待证事实与争点。AI 可提出映射候选，但状态必须为 ai_proposed。
3. fact_position_links：待证事实与诉请或抗辩。target_type 决定 target_id 应指向 claims 或 defenses。

关系状态不是实体结论：ai_proposed 表示待律师复核，human_confirmed 表示用户显式确认，disputed 表示存在争议。

## 来源定位

每个 source_span 必须包含非空 quote，并至少提供一种可回查位置：

- page：从 1 开始的页码；
- paragraph：从 0 开始的段落序号；
- start 或 end：文本字符位置。

定位仅用于回查，不代表引文已通过真伪审查。

## 三性记录

evidence 中的 authenticity、legality 和 relevance 保持共享 Schema 的状态。默认使用 unreviewed 或 unknown。只有在 three_nature_reviews 存在对应维度、对应状态和人工确认记录时，才能填写 accepted 或 disputed。

脚本只校验记录闭环，不验证确认人身份、不将记录升格为律师意见。

## 输出语义

- coverage 只表示是否建立了结构化链接，不表示证明力。
- gaps 是机器可识别的断链或待确认项，不自动转换为举证建议。
- potential_conflicts 是同字段不同值、事实冲突状态或人工声明的冲突候选，须人工核实。
- artifact_state 固定为 lawyer_review_required。

## 输入 Schema 硬约束（2026-08-09 测试补正）

- `sources[].sha256` 必须匹配 `^[a-f0-9]{64}$`（63 位即校验失败）；
- `issues[].status` 枚举：`open / partially_supported / supported / disputed / blocked`（无 `undisputed`）；
- `claims[].amount` 为 number 且**不能为 null**——违约金类金额不明时省略该字段而非填 null；
- `evidence[].fact_ids` 与 `evidence_fact_links` 必须一一对应（双向校验，缺一边即失败）。
