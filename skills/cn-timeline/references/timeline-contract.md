# 时间轴数据契约

## 一、日期精度

| 精度 | 规范化方式 | 示例 |
|---|---|---|
| `exact` | `start` 与 `end` 为同一天 | 2026-07-18 |
| `month` | 月初至月末 | 2026-07 |
| `year` | 年初至年末 | 2026年 |
| `range` | 明确记录起止日期 | 2026-07-01至2026-07-18 |
| `unknown` | 不填写 `start`、`end` | 去年夏天左右 |

脚本不负责把自然语言日期推断为精确日期。无法确认时保留 `raw` 并使用 `unknown`。

## 二、事件状态

- `stated`：某一来源如此陈述；
- `user_confirmed`：用户明确确认，但不等于法院认定；
- `derived`：依确定性规则推导，须记录规则；
- `disputed`：其他主体明确否认；
- `missing`、`conflict`、`unreadable`：分别表示缺失、冲突或无法识别。

## 三、冲突识别

`comparison_key` 只用于标识“这些记录声称描述同一现实事件”。相同键下的日期区间互不重叠时，脚本生成冲突，不删除任一记录。不同来源描述不同履行批次时不得共用同一个键。

## 四、期限触发候选

`deadline_trigger_candidate` 只表示该事件可能成为起算事实。是否构成法定起算点、适用何种规则、是否顺延或中止，必须交 `cn-deadline` 并由律师核验。

## 五、向期限计算移交

对 `deadline_trigger_candidate=true` 的事件按下表移交，不复制自由文本结论：

| `cn-timeline` | `cn-deadline` | 处理规则 |
|---|---|---|
| `matter_id` | `matter_id` | 必须完全一致 |
| `event_id` | `deadlines[].event.event_id` | 保持稳定编号 |
| `date.raw` | `operative_date_basis` | 作为原始日期说明的一部分保留 |
| `date.start` | `operative_date` | 只有 `precision=exact` 且律师确认该日为法律起算日后才能复制 |
| `source_spans` | `evidence_locator` | 合并为可回查材料定位，不只写事件描述 |
| `status`、日期冲突 | `blocking_questions` | 非 `user_confirmed`、非精确日期或存在冲突时必须阻断 |

`cn-deadline` 的 `confirmed_by_human` 只能由有权办案人员设置；时间轴中的 `user_confirmed` 仅表示事实日期经用户确认，不自动等于法律起算点已经律师确认。
