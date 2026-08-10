# 案件生命周期契约

允许状态：`intake`、`active`、`on_hold`、`closing`、`closed`。

控制状态只能为 `confirmed`、`pending` 或 `not_applicable`；`not_applicable` 必须有人工确认说明。任务状态只能为 `pending`、`completed` 或 `cancelled_confirmed`。期限仅保存 `deadline_id` 引用，具体计算交由 `cn-deadline`。

脚本生成新的状态快照和审查报告，不更新律所系统。所有实际状态变更仍需负责人按本所制度审批。
