# 期限计算输入契约

## 基本原则

每个输入文件以 `as_of_date` 作为本次计算的知识截止日，包含一组可选日历和一组期限任务。完整结构见 `schemas/deadline-input.schema.json`。

## 起算事件

- `occurred_at`：带 UTC 偏移的证据记录时间，可选。
- `operative_date`：已由办案人员确认的法律起算日，是计算程序的唯一起点。
- `operative_date_basis`：说明为何选择该日期，并定位送达回证、系统回执、签收记录或内部审批记录。
- `confirmed_by_human`：必须为 `true` 才进入计算；为 `false` 时输出阻断项。

## 规则与来源

规则不是自由文本中的“天数”，而是以下两类显式计算法之一：

- `counted_days`：计数法。设置 `count`、`day_kind` 为 `calendar` 或 `working`，并明确是否计入起算日。
- `anniversary`：周年日法。设置 `unit` 为 `months` 或 `years`、`count`，以及目标月无对应日时是取月末还是阻断。

规则的 `source` 必须记录：

- 来源类型、名称、条款或文件定位、与期限计算直接相关的原文摘录；
- `effect_status`，可为 `effective`、`not_yet_effective`、`repealed`、`superseded` 或 `unknown`；
- `verified_on` 和可回查的 `url` 或 `document_locator`。

只有 `effect_status` 为 `effective` 且 `verified_on` 不晚于 `as_of_date` 的来源才可支持自动计算。脚本不联网判断效力，也不使用内置法条表。

## 工作日日历

当规则计算工作日，或要求到期日顺延、前移到工作日时，引用的日历必须：

- 与任务时区一致；
- 声明覆盖起止日，并将 `declared_complete` 设为 `true`；
- 单独列出 `non_working_dates` 和调休 `working_dates`；
- 记录日历发布来源和核验日期。

日期判定顺序为：显式非工作日 → 显式调休工作日 → 周末集合 → 普通工作日。

## 显式调整

调整按输入顺序执行，每项均要记录原因和已核验来源：

- `add_days`：从当前候选日期起再增加明示天数，可选日历日或工作日。
- `set_date`：将候选日期替换为已由办案人员确认的指定日期。

中止、中断、扣除期间等法律效果未经人工确认时，写入 `blocking_questions`，不自动换算为天数。
