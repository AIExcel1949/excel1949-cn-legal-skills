---
name: cn-contract-draft
description: 根据律师或用户已确认的交易清单、当事人角色、商业条款、风险分配、定义和已核验法源记录，生成中国合同的条款结构、Markdown 底稿、JSON 追溯记录以及缺口、冲突和交叉引用报告。在起草、改写或组装买卖、服务、借款等合同底稿时使用；不用于补造商业条款、默认接受模板、自动签署、盖章、发送或对外提交。
---

# 中国合同结构化起草

## 流程

1. 先确认代表立场、法域、交易清单、当事人角色、商业条款和风险分配；未确认内容不得补写。
2. 必要时读取 `domain-packs/contract-obligations/pack.json` 建立问题清单，但不得将业务包当作现行法依据。
3. 通过 `cn-research` 核验每个引用法源的效力、全文、时间效力和适用性。
4. 按 [references/input-output-contract.md](references/input-output-contract.md) 组织输入，运行：

   ```bash
   .venv/bin/python skills/cn-contract-draft/scripts/build_contract_draft.py input.json \
     --json-output /path/to/new-draft.json \
     --markdown-output /path/to/new-draft.md
   ```

5. 逐项处理缺口、冲突和交叉引用异常，再由执业律师审查条款表达、风险分配与法律适用。

## 硬性边界

- 仅将状态为 `confirmed` 的输入组装进底稿；不从交易类型、行业习惯或模板推定金额、期限、责任或接受意思。
- 模板文本只能作为明示来源材料，不得默认纳入、默认接受或冒充已谈妥条款。
- 未确认代表立场、法域、必需交易项或被引用项时，输出阻断而非自动修复。
- 失效、未核验、未查看全文或未确认适用的法源不得支撑条款。
- 只生成 JSON 和 Markdown 工作底稿，不生成已签署版，不自动发送、提交、签名或盖章。

## 质量门禁

- 输出保留规范化输入 SHA-256、每个条款的来源项和法源引用。
- 相同业务键、风险主题或定义出现不同已确认值时，必须显示冲突。
- 条款引用不存在的交易项、风险项、定义或法源时，必须显示缺口并阻断。
- 产物状态固定为 `lawyer_review_required`，输入不得覆盖该状态。

