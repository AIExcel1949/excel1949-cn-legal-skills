# 检索报告数据契约

报告由六部分组成：

1. 任务和时间截点；
2. 检索问题与检索矩阵；
3. 检索日志；
4. 法源卡和案例卡；
5. 分问题结论、反方观点和限制；
6. 人工复核清单。

## 核验状态

| 状态 | 含义 |
|---|---|
| `pending` | 只获得线索或摘要，尚未核对原文 |
| `source_opened` | 已打开原文，但引用和效力尚未全部核验 |
| `verified` | 已核对原文、定位、效力或案例身份 |
| `failed` | 链接、原文或关键信息无法核验 |

任何结论引用的来源都必须为 `verified`。`failed` 和 `pending` 可进入限制清单，但不能支撑正式结论。

## 报告状态

只允许 `draft`、`machine_checked`、`lawyer_review_required` 和 `lawyer_reviewed`。AI 生成报告后最多标记为 `lawyer_review_required`。

