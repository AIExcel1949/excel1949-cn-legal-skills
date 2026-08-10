# 输入输出契约

## 输入

- `review_context`：代表立场和法域必须由用户确认。
- `transaction_checklist`：必需项只能为“已确认”或“缺失”；“不适用”必须保留理由。
- `parties`：当事人名称和角色必须明示确认，脚本不推定甲乙方身份。
- `commercial_terms`：`value` 是输入者确认的原始商业表达，脚本不换算、补齐或解释。
- `risk_allocations`：`allocation` 仅记录确认的风险安排。
- `definitions`：定义与含义必须确认；不同含义的同名定义会产生冲突。
- `authority_records`：条款引用的法源必须为现行有效、已核验、已查看全文且已确认适用。
- `clause_plan`：只组装对其他项的 ID 引用，不得把自行补写的条款文字伪装成确认输入。

## 输出

- `draft.clauses[].body_lines` 只是对确认输入的确定性组装。
- `gaps` 记录缺失、未确认和无法解析的引用。
- `conflicts` 记录同一业务键、风险主题或定义的不一致已确认值。
- `cross_reference_report` 显示缺失引用和未被使用的定义。
- `blocked=true` 表示不得把该底稿作为签署或对外版本。

Markdown 与 JSON 均是工作底稿，不是签署版合同或最终法律意见。

