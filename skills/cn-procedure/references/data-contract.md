# 案件数据契约

## 目录

1. 稳定性结论
2. 字段分组
3. 填写规则
4. 一致性规则
5. 兼容策略

## 稳定性结论

`{{lawyer_name}}` 是模板定位标记，不是稳定性机制。只有字段名称、数据类型、必填条件、默认值、派生规则和失败策略同时固定后，键值对才适合批量生成。

本 Skill 使用扁平、版本化 JSON，原因是便于律师查看、Excel 导出和模板直接替换。字段数量继续增长时，可在下一个主版本调整为嵌套结构；同一主版本内不得静默改名。

## 字段分组

### 控制字段

- `schema_version`：固定为 `1.0`。
- `procedure_type`：`civil`、`criminal`、`administrative`、`enforcement`、`nonlitigation` 之一。
- `document_date`：数据文件制作日期，格式为 `YYYY-MM-DD`。

### 案件字段

- `case_cause`：案由或事项名称。
- `case_court`：法院或办案机关全称。
- `case_number`：已有案号；尚无案号时留空，不得编造。
- `doc_number`：律所内部函号，由律所编号系统产生。
- `litigation_stage`：代理阶段。
- `disputed_amount`：争议标的额，只填数字和小数点（机器校验值，如 `14000000.00`）。
- 金额展示规范（BUG-G 修复）：文书正文中的金额一律统一为“千分位阿拉伯数字 + 元”（如 `14,000,000.00 元`）或“中文大写（壹仟肆佰万元整）”，禁止同一文书内“1,400 万元”与 `14000000.00 元` 两种格式混用；数据提供方在正文/占位文本中统一格式后再填充。
- `execution_basis`：执行依据名称。
- `judgment_court`：执行依据作出机构。
- `judgment_effective_date`：执行依据生效日期。
- `judgment_main_text`：执行依据判项主文（原文摘录）。
- `execution_claims`：申请执行事项（逐项列明，对齐法〔2025〕82号强制执行申请书要素）。
- `preservation_status`：是否有诉前/诉讼保全（填“有”或“无”及简要情况）。
- `property_clues`：其他财产线索；无则填“暂无”。

### 主体字段

- `client_name`、`client_id`、`client_address`、`client_phone`、`client_credit_code`。
- `client_identity_description`：财产保全等需要完整主体信息的文书使用，应填写主体类型、证件类型及号码；不得只写“详见材料”。
- `opponent_name`、`opponent_identity_description`、`opponent_address`、`opponent_phone`。
- `criminal_subject_name`：犯罪嫌疑人、被告人或刑事诉讼代理对象；不得与委托人混同。
- `criminal_role`：`辩护人` 或 `诉讼代理人`。
- `principal_relationship`：刑事委托人与被辩护人之间的关系。
- `agent_name`、`agent_id`、`agent_phone`、`relationship`：仅近亲属或其他公民代理使用。
- `client_legal_rep`、`client_legal_rep_id`、`client_legal_rep_title`：法人主体按需使用。
- `employee_name`、`employee_id`、`employee_phone`、`employee_title`：单位工作人员代理使用。

### 律所与律师字段

- `lawyer_name`、`lawyer_license`。
- `assistant_name`、`assistant_license`：选填，不得把实习证号写成律师执业证号。
- `firm_name`、`firm_address`、`firm_phone`。

### 授权与收费字段

- `authorization_scope`：旧版二选一模板兼容字段，只能为 `（1）`、`（2）` 或空字符串；新制作的民事、行政授权书不再依赖该字段。
- `authorization_scope_text`：民事、行政代理使用。一般授权填“一般授权”；特别授权可填“特别授权”（概括式），也可填逐项明细，如“特别授权：代为承认、放弃、变更诉讼请求，进行和解、调解，提起反诉、上诉，申请执行，代收法律文书及款项等”（BUG-F 修复：模板占位符为自由文本，支持逐项列示，由承办律师确认）。
- `authorization_period`：写明起止时间，或填写经委托人确认的本审级期限。
- `criminal_stages`：刑事阶段编号组合，例如 `（1）（2）`；由委托人确认。
- `fee_amount`：小写金额，例如 `20000.00`。
- `fee_amount_cn`：中文大写金额，例如 `人民币贰万元整`。
- `fee_payment_terms`：经双方确认的支付节点、期数和收款账户类型；不得由 AI 默认设置。
- `case_expense_terms`：分别约定诉讼费、保全费、担保费、鉴定费、公证费、评估费、差旅等第三方费用或工作费用的承担和结算方式。
- `annual_fee`、`annual_fee_cn`：法律顾问费。
- `risk_fee_terms`：风险代理的协商结果；不得由 AI 自动决定。
- `risk_agency_confirmed`：仅在人工排除禁止范围并核对现行上限后填 `yes`；不得设置默认值。

### 财产保全字段

- `preservation_request`：写明冻结、查封、扣押等具体措施、财产对象和金额上限。
- `preservation_necessity`：陈述可能导致判决难以执行或者造成其他损害的具体事实，不得使用空泛结论替代。
- `property_clues`：填写已知账户、不动产、车辆、股权等线索；确无具体线索时如实说明，不得编造。
- `security_method`：填写保函、保证金、财产担保，或者依法不要求提供担保的具体依据。
- `attachments`：列明申请依据、财产线索、担保材料及主体资格材料。

### 日期字段

模板显示值统一为中文日期，例如 `2026 年 7 月 17 日`。JSON 中可直接提供该显示值；需要计算或比较的日期另用 ISO 格式字段，不混用。

## 填写规则

1. 不知道的选填字段使用空字符串；必填字段缺失时停止生成。
2. 不使用 `待定`、`同上`、`略` 填充身份证号、联系方式、授权范围和收费。
3. 不把多个主体塞入一个字段；共同委托人应在未来的多主体版本中用数组表达，当前版本须逐份确认模板是否支持。
4. 文件名由模板清单控制，并对 `/`、`:` 等非法字符进行清理。
5. JSON 的双引号是语法字符，不适用中文文档引号替换。

## 一致性规则

- 同一输出批次只读取一份 JSON。
- `case_cause`、`client_name`、`opponent_name`、`lawyer_name`、`firm_name` 不得在单份模板中被局部改写。
- `fee_amount` 与 `fee_amount_cn` 必须人工交叉核对。
- `case_number` 为空时，不生成看似真实的占位案号。
- `authorization_scope` 和 `criminal_stages` 不设默认值。

## 兼容策略

字段只允许在小版本中新增，不允许改义。需要改名时：

1. 在新主版本中增加新字段；
2. 保留旧字段读取兼容；
3. 明确输出弃用警告；
4. 更新 schema、模板清单、示例和测试；
5. 不在同一次升级中同时改变字段含义和模板法律逻辑。

- `filing_date`：起诉/立案日期（撤诉申请书用）。
- `fee_refund_request`：诉讼费退还请求说明（如“请求退还已预交的诉讼费”）。
- `preservation_ruling_number`：原保全裁定案号（解除保全申请书用）。
- `release_scope`：解除保全的范围（如“全部财产”或指定账户/财产）。
- `release_reason`：解除保全的事由（和解、提供担保、保全错误等）。
- `bank_accounts`／`real_estate_clues`／`vehicle_clues`／`other_assets_clues`：网络查控对象明细（开户行与账号、不动产、车辆、证券与网络资金等；无则填“暂无”）。
- `execution_necessity`：网络查控/执行必要性说明。
- `original_claims`：变更前的原诉讼请求原文。
- `change_reason`：变更诉讼请求的事由。
- `additional_protective_measures`：人身安全保护令的其他保护措施（无则填“暂无其他措施”）。
- `domestic_violence_facts`：遭受家庭暴力或面临现实危险的事实经过。
- `protection_evidence`：人身安全保护令申请的证据清单（报警记录、伤情照片、医院诊断等）。