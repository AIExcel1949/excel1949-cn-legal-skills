# 输入输出契约

## 来源约束

- `source_span`：必须同时登记 `source_id`、原文引文 `quote` 和页码、段落或字符位置 `locator`。
- `user_confirmed`：必须登记 `confirmed_at` 和具体 `confirmation_note`，只表示用户提供，不表示真实或法律成立。
- 申请请求与支撑事实不得使用模型推断作为来源。

## 法源与特殊结论

- 每个法源必须有效力状态、核验日期和官方或可回查地址。
- `deadline_review` 和 `security_review` 默认为 `unverified`。如登记为 `verified`，必须引用已核验法源并保留律师复核。
- 本 Skill 不计算期限，不推定担保是否必要及其数额。

## 生成结果

`application-workpaper.json` 保留原始请求、事实、法源和材料，并添加路由清单、材料缺口和待律师复核项。《程序申请工作底稿.md》是同一数据的人工复核视图，不是可直接提交的申请书。
