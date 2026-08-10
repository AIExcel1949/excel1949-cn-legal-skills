---
name: cn-applications
description: 为中国律师诉讼、仲裁和执行实务路由并编排程序申请工作底稿，覆盖保全、证据保全、调查取证、鉴定、延期、中止和回避等申请的请求、事实来源、要件、材料、紧急性与缺口清单。用于申请类型初步分流、材料收集和提交前律师复核；不硬编未核验期限或担保结论，不自动签章、提交或对外发送。
---

# 中国程序申请清单

## 执行流程

1. 先核对案件编号、程序阶段、受理机构和申请类型；类型不明时使用 `other` 并列入待律师选择。
2. 对每项申请请求和支撑事实登记原文来源，或登记用户明确确认的时间与说明。
3. 根据类型生成通用工作清单；详细路由见 [references/application-routing.md](references/application-routing.md)。
4. 将法律要件、期限、担保和受理要求作为待核验项，只能引用已登记法源或律师确认，不由脚本自行下结论。
5. 运行确定性生成器：

```bash
python scripts/build_application.py examples/application.example.json --output /path/to/new-output
```

输入输出契约见 [references/input-output-contract.md](references/input-output-contract.md)。

## 阻断条件

- 请求或支撑事实既无原文来源，也无 `user_confirmed` 记录；
- 法源缺少效力状态、核验日期或可回查地址；
- 将未核验期限、担保方式或担保数额写成确定结论；
- 用户要求自动签名、盖章、发送或提交；
- 输出目录已存在。

## 输出门禁

- 输出 `application-workpaper.json`（内部数据）和《程序申请工作底稿.md》（交付给用户的默认产物，不向用户直接交付 JSON）；
- 需要正式申请书 DOCX 时，由 `cn-procedure` 按法〔2025〕82号示范文本要素生成（如强制执行申请书、财产保全申请书），本 Skill 不直接输出正式申请书；
- `artifact_state` 始终为 `lawyer_review_required`；
- 清单仅表示工作项，不表示要件已成就或申请必然获准；
- 采用临时目录后原子改名，不覆盖旧结果。
