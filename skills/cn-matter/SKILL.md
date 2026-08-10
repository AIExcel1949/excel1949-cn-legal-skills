---
name: cn-matter
description: 管理中国律师案件从咨询、收案、承办、暂停、结案到归档的状态流转、任务清单、期限引用、交付物和人工控制门禁。用于建立案件状态快照、检查能否进入承办或结案阶段、汇总未完成任务和生成归档审查底稿；不用于自动通过利益冲突、收费、用章、签署、结案或删除案件材料。
---

# 中国律师案件全生命周期管理

## 执行流程

1. 读取 `cn-intake`、`cn-deadline` 和各工作流产生的稳定编号，不复制或改写正文。
2. 由律所人工流程明确当前状态、目标状态和每项控制的确认状态。
3. 运行确定性状态机：

```bash
.venv/bin/python skills/cn-matter/scripts/build_snapshot.py \
  skills/cn-matter/examples/matter.example.json \
  --output /path/to/new-snapshot
```

4. 处理阻断项后由负责人决定是否实际变更案件管理系统；脚本不写入外部系统。

状态和控制字段见 [references/lifecycle-contract.md](references/lifecycle-contract.md)。

## 状态边界

- `intake → active` 必须由人工确认冲突检查、委托手续和收费安排。
- `active → on_hold/closing` 必须有已确认原因；暂停不代表期限停止。
- `closing → closed` 必须完成最终复核、任务处置、账务核对、归档清单和保管分类。
- 任何情况下都不自动盖章、发送、提交、销毁、删除或覆盖案件文件。
- 输出固定为 `lawyer_review_required`，通过机器状态机不等于律所审批通过。
