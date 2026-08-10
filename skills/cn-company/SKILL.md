---
name: cn-company
description: 将中国公司主体、章程版本、股东及董监高名册、议题、权限依据和会议行动整理为可追溯的 JSON 与 Markdown 公司治理任务矩阵。用于股东会或董事会筹备、书面决议、任免、资本事项以及登记或披露前的内部核查；不自动认定决议有效，不代签，不提交市场监管登记或信息披露。
---

# 中国公司治理任务矩阵

## 执行流程

1. 核对公司类型、登记快照及核验时点；对统一社会信用代码等敏感信息先脱敏。
2. 分列章程历史版本、当前版本和草案。当前章程未确认或存在两个以上“当前版本”时，不选择版本。
3. 登记股东、董事、监事和高级管理人员名册及各自来源，不以未经核验名册补齐事实。
4. 将每项议题绑定拟议决策机构、章程版本和权限依据。法源登记口径见 [references/company-governance-rules.md](references/company-governance-rules.md)。
5. 按 [schemas/company-input.schema.json](schemas/company-input.schema.json) 准备输入并生成底稿：

   ```bash
   python scripts/build_company_matrix.py input.json --output output/company-matrix
   ```

6. 由执业律师复核决策权限、召集、通知、表决、回避、签署、登记与披露要求，再决定是否另行制作文件或办理事项。

## 强制门禁

- 仅使用输入中的权限规则和已登记来源；不得内置或猜测法定比例、通知期限、登记期限。
- 任何议题缺少权限来源、当前章程不唯一、行动缺少议题、登记或披露必要性未确认时，输出对应阻断项。
- 固定输出 `resolution_validity_determined: false`、`external_submission_performed: false` 和 `artifact_state: lawyer_review_required`。
- 不生成签名、印章、提交回执或“决议有效”结论。
- 输出目录必须不存在；脚本以同文件系统临时目录和原子更名落盘，拒绝覆盖。

## 输出

- `company-matrix.json`：主体快照、章程门禁、议题权限映射、任务矩阵、阻断项及告警。
- `company-matrix.md`：供律师逐项复核的可读底稿，不是正式决议、会议通知或登记申请。

## 对外使用提示

1. AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。
2. 使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。
3. AI 不能替代律师对案件具体情况进行独立法律判断。
4. 本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。
5. AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。
