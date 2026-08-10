---
name: cn-timeline
description: 从中国法律案件材料、当事人陈述和程序文书建立可回查的事实时间轴与程序时间轴，规范日期精度，识别同一事件的日期冲突、先后关系异常和期限触发候选。用于诉讼、仲裁、执行、刑事、行政及非诉调查；不自行认定争议事实，不直接计算法定期限。
---

# 中国案件时间轴

## 执行流程

1. 每个事件只记录一个可描述的发生事项，并保留原始日期文字。
2. 区分精确日期、月份、年份、区间和未知日期；不得把低精度日期补成某日。
3. 为指向同一现实事件的记录设置相同 `comparison_key`，让脚本识别日期冲突。
4. 分开记录事实事件、程序事件、付款、沟通、证据形成和其他事件。
5. 仅把可能触发期限的事件标为 `deadline_trigger_candidate`，不得直接得出截止日。
6. 运行脚本生成排序时间轴、冲突表和待核验项。从项目根目录使用 `.venv` 运行；首次使用先按根目录 `requirements.txt` 安装 `jsonschema` 等依赖：

```bash
python scripts/build_timeline.py examples/timeline.example.json --output /path/to/new-timeline-output
```

日期结构、冲突规则以及向 `cn-deadline` 移交字段的方式见 [references/timeline-contract.md](references/timeline-contract.md)。

## 阻断条件

- 事件编号重复，或日期起点晚于终点；
- `exact` 日期不是同一天；
- 已确认事件没有来源或人工确认说明；
- 同一 `comparison_key` 出现互不重叠日期，但未进入冲突清单；
- 用户要求把模型推测日期直接写成已确认事实。

## 输出门禁

- 原始日期、规范化日期和日期状态必须同时保留；
- 未知日期排在时间轴末尾，不得伪造排序键；
- 冲突记录保持并列，不自动择一；
- 输出只标记期限触发候选，交由 `cn-deadline` 按已核验规则计算；
- 所有结果写入新目录，不覆盖输入。
