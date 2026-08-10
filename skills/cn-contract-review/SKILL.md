---
name: cn-contract-review
description: 对用户提供的中国合同文本快照逐字保留、文件与条款哈希，并逐条生成 issue、risk、source、authority、suggestion 和 delta 分离的可追溯审查报告及红线变更指令。在审查、复核、谈判或比对买卖、服务、借款等合同条款时使用；不用于静默修改原文、替当事人确认代表立场、将风险提示写成确定无效结论，或自动签署、发送和提交合同。
---

# 中国合同逐条审查

## 流程

1. 将本次审查版本导出为 UTF-8 纯文本快照，保留该快照文件的 SHA-256。
2. 确认代表立场、法域和合同版本；任一项未确认时只生成阻断报告。
3. 以字符偏移和原文匹配逐条记录原条款，不改写 `original_text`。
4. 必要时读取 `domain-packs/contract-obligations/pack.json` 建立问题清单，但在引用前必须通过 `cn-research` 重新核验现行法源。需要检查条款缺项、定义词或交叉引用时，按 [references/review-contract.md](references/review-contract.md) 建立显式台账，不靠关键词自动判定。
5. 按 [references/review-contract.md](references/review-contract.md) 组织输入，运行：

   ```bash
   .venv/bin/python skills/cn-contract-review/scripts/review_contract.py input.json \
     --source-contract contract-snapshot.txt \
     --json-output /path/to/new-review.json \
     --markdown-output /path/to/new-review.md
   ```

6. 将建议文本、红线指令与原文分离交付，由执业律师选择是否采纳和实际修改。

## 必须阻断

- 代表立场、法域或版本未由用户确认。
- 源文件 SHA-256 不匹配，条款字符偏移越界，或 `original_text` 与源文逐字不同。
- 法律类风险意见没有可回查法源，或引用法源失效、未核验、未查看全文、未确认适用。
- 风险意见使用“条款无效”、“必然无效”、“当然无效”、“确定无效”或“绝对无效”等未经裁判的确定性表述。
- 红线指令的目标文本不是原条款的逐字子串，或替换指令没有独立建议文本。

## 边界与门禁

- 原条款、建议文本和变更指令必须分字段存储；脚本不执行 delta，不改动源文件。
- 商业风险和起草质量问题可以不引法条，但必须保留原文来源；法律问题必须引用已核验法源。
- “可能存在风险”和“待核验”是风险筛查状态，不是无效、违约或责任成立的确定结论。
- 输出路径已存在时拒绝覆盖；产物状态固定为 `lawyer_review_required`。
