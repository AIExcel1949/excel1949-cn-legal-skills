---
name: cn-defense
description: 将原告诉请、cn-case-analysis、cn-evidence-map 和 cn-research 成果转换为中国民事答辩状的逐项答辩矩阵与 Markdown 草案，保留承认、否认、不知悉、程序异议及未回应状态、来源和举证缺口。用于按诉请编号整理已有答辩指示，并生成待执业律师复核的结构；绝不将未回应视为承认，不推断抗辩、不签章、不直接提交。
---

# 生成逐项答辩矩阵

1. 读取 `references/contract.md`，使用 `schemas/defense-input.schema.json` 准备输入。
2. 为每项原告诉请仅登记用户明示给出的 `admit`、`deny`、`lack_knowledge` 或 `procedural_objection`。不得从沉默推断立场。
3. 运行：

```bash
python scripts/build_defense.py --input <input.json> --output-dir <new-directory>
```

4. 检查 `defense.json` 的 `response_matrix`、`blockers` 和 `evidence_gaps`。没有对应回应的诉请必须保留为 `unanswered` 并阻断。
5. 将产物交由执业律师独立判断和复核。`artifact_state` 始终为 `lawyer_review_required`。

所有诉请、答辩、事实和独立抗辩必须具有 `source_spans` 或 `user_confirmed: true`。缺失来源直接拒绝生成；冲突、待确认项、证据缺口和未核验法源必须阻断。禁止生成签名或印章。需要 DOCX 时只能后续复用 `cn-legal-core` 品牌能力，作者为 `AIOffice职场通关-excel1949`。
