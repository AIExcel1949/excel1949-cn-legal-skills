# 输入输出契约

## 输入分区

`negotiation-input.schema.json` 将输入分为两个互不嵌套的区域：

- `internal_strategy`：仅存放客户授权、内部目标、底线、BATNA、议题优先级、评估标准、方案评分和内部备注。
- `external_workspace`：仅存放经披露复核的对外编号、议题、提案、条件式让步交换和会议纪要。

`matter_id` 只进入内部工作簿。对外预览仅使用单独录入的 `external_reference`，不会自动携带内部案件标识。

## 引用约束

- `issue_id` 在对外议题中唯一；内部优先级、底线、授权和对外提案可引用它。
- `proposal_id` 在对外提案中唯一；内部方案评估必须与之一一对应。
- `criterion_id` 在评估标准中唯一；每个方案必须对所有标准各评分一次。
- 评估权重合计必须等于 100。加权分仅供并列比较，不输出排名或推荐。
- 让步交换必须同时给出 `give_text`、`receive_text` 和 `condition_text`，状态固定是“提议”。

## 会议纪要

`tentative_items.status` 只能是 `pending`、`confirmed` 或 `rejected`。这些状态是纪要归类，不是对外承诺。脚本将所有 `pending` 项复制到对外预览的 `pending_confirmations`，避免“暂定项”被遗漏。

## 输出

### 内部工作簿

`negotiation-workbook.schema.json` 要求：

- 完整保留内部策略，并明示标记仅限内部使用；
- 按优先级整理议题，按明示权重计算方案得分；
- 列出未确认授权、待确认提案和会后待办；
- 仅保存对外预览 SHA-256，不在内部工作簿中嵌入对外文本。

### 对外预览

`external-preview.schema.json` 的字段白名单只允许：对外参考号、基准日、议程、提案、条件式交换、会议纪要、待确认项、声明和行为控制。所有对象均禁止未定义字段。

两份输出都是 UTF-8 JSON，都拒绝覆盖，都不是可直接发送或签署的文件。
