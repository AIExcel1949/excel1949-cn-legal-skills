# 收案数据契约

## 一、信息分层

- `request.raw_request`：保留当事人的原始目标，不替换为案由或请求权。
- `participants`：只记录身份、角色和名称状态；关系存在争议时分别记录。
- `materials`：记录文件名、SHA-256、取得方式和解析状态，不修改原件。
- `statements`：一项陈述只表达一个事实字段；原值与规范化值分开。
- `controls`：记录必须由律师或律所流程确认的门禁，不由 AI 自动清除。

## 二、状态解释

事实状态沿用 `cn-legal-core`：

- `stated`：仅为当事人或材料中的陈述；
- `user_confirmed`：用户明确确认，但不等于证据已经证明；
- `derived`：由确定性规则推导，必须记录规则；
- `disputed`：对方或其他材料明确否认；
- `missing`：尚未提供；
- `conflict`：多个来源互不一致；
- `unreadable`：材料无法可靠识别。

风控状态使用 `not_started`、`pending`、`cleared`、`blocked` 或 `not_applicable_confirmed`。只有人工流程才能设置 `cleared` 和 `not_applicable_confirmed`。

同一字段出现不同说法时，每个来源分别建立一条 `statement`，使用不同 `statement_id`，保留各自 `source_spans`，并把相关记录标为 `conflict`。不得把两个互斥值合并进一条多来源陈述，也不得由脚本选择其中一项。

## 三、强制人工门禁

以下项目不得由模型自行判断：

1. 利益冲突是否通过；
2. 委托人和代理权限是否核验；
3. 诉讼时效、除斥期间或程序期限是否存在风险；
4. 是否申请保全、行为禁令、人身保护或其他紧急措施；
5. 是否承办、收费方式、风险代理和特别授权。

## 四、输出解释

- `blocked`：存在明确阻断项；
- `needs_information`：缺少事实或材料；
- `ready_for_lawyer_decision`：数据足以进入律师判断，但不表示承办、无冲突或法律结论成立。
