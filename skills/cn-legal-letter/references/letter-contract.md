# 律师函输入契约

每项事实和要求必须具有 `source_spans`，或由用户明确确认并填写 `confirmation_note`。法源必须记录官方 URL、核验日期、全文核对状态和效力状态。金额工作纸仍是旁路计算，只有 `lawyer_confirmed=true` 时才能进入底稿。

`external_action_requested` 必须为 `false`。渠道列表仅用于人工送达计划，不触发电子邮件、短信、快递或任何第三方服务。
