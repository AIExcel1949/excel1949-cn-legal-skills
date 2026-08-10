---
name: cn-employment
description: 对中国劳动用工材料进行全周期结构化审查，整理劳动关系识别候选、招聘入职、劳动合同、规章制度、工资工时休假、社保福利、变更解除终止、离职交接和劳动争议，并生成保留原文、来源、哈希与核验状态的 JSON 工作簿和 Markdown 报告。在律师审查用工安排、人事制度、拟议人事行动或劳动争议时使用；不用于自动认定违法、作出不利人事决定、发送通知、执行解除或向任何机构提交材料。
---

# 中国劳动用工全周期审查

## 执行流程

1. 将原始材料逐份录入 `sources`，保留原文、来源定位、SHA-256 和核验状态。脚本会重算原文哈希，不一致即阻断。
2. 将管理与从属、工作整合、报酬、工具、时间地点等观察写入 `relationship_review.signals`，仅标记它们支持的关系候选，不让脚本自动定性。
3. 按 [references/input-contract.md](references/input-contract.md) 将全部用工阶段归入 `lifecycle_reviews`，每个事项同时保留事实来源、法源候选、待研究问题和律师复核状态。
4. 只从 [references/official-sources.json](references/official-sources.json) 选择已登记法源 ID，并核对 [references/official-sources.md](references/official-sources.md) 记载的时点与适用边界。
5. 从项目根目录使用 `.venv` 运行：

   ```bash
   python skills/cn-employment/scripts/build_employment_review.py input.json \
     --json-output employment-review.json \
     --markdown-output employment-review.md
   ```

6. 由执业律师结合用工地、用人单位性质、集体合同、地方规则、事实与证据作出最终判断。

## 必须覆盖

- `recruitment_onboarding`：招聘条件、入职材料、告知与背景核验。
- `labor_contract`：合同类型、书面文本、试用、工作内容与地点。
- `work_rules`：规章制度的制定、协商、公示、告知与执行记录。
- `pay_hours_leave`：工资、工时、加班、休息、休假与记录链。
- `social_insurance_benefits`：社会保险、福利和待遇材料。
- `change_termination`：变更、解除、终止的事实基础、程序、授权与文书候选。
- `exit_handover`：离职交接、工资结算、证明、档案与社保转移线索。
- `labor_dispute`：调解、仲裁、诉讼、时效、举证与请求候选。

## 行为边界

- 劳动关系类型、违法性、解除事由、赔偿责任和争议结果始终标记为“候选”或“待律师判断”。
- 不基于性别、年龄、民族、残疾、婚育、健康或其他受保护因素推荐录用、降薪、调岗、惩戒或解除。
- 不把人事制度文本的存在直接视为已完成民主程序、公示或送达。
- 不自动生成可发送的解除、终止、惩戒、录用或仲裁通知，不执行、发送、提交、签署或盖章。

## 输出门禁

- 原文哈希不匹配、来源引用断裂、法源 ID 未登记、编号重复或输出路径已存在时阻断。
- 缺失的用工阶段必须列入 `coverage_gaps`，不得默认为无风险。
- 所有不利人事行动候选都必须进入 `human_decision_queue`，不输出自动建议。
- 作者固定为 `AIOffice职场通关-excel1949`，终态固定为 `lawyer_review_required`，所有决定、通知、解除、提交、签署和盖章控制固定为 `false`。
- JSON 与 Markdown 通过临时文件和硬链接原子新建，拒绝覆盖。
