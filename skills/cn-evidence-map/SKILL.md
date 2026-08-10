---
name: cn-evidence-map
description: 为中国律师诉讼、仲裁和非诉事实核验建立证据—待证事实—争点—诉请或抗辩的可回查关系，生成证据矩阵、证据缺口、潜在冲突、三性审查状态和来源定位报告。用于证据目录梳理、庭前准备、诉讼请求或抗辩的证据覆盖检查；不用于自动认定真实性、合法性、关联性，不虚构证明目的，不转写庭审录音。
---

# 中国证据映射

## 执行流程

1. 核对案件编号、材料截止日期和来源清单，不把缺失值填成模型推测值。
2. 分别登记原文事实、争点、诉请、抗辩和证据，保留来源定位。
3. 只记录材料明载或用户明确确认的证明目的；其余标记为缺口。
4. 将 AI 建议的事实—争点、事实—诉请或抗辩关系标记为 ai_proposed，不得写成已经律师确认。
5. 运行确定性校验与报告脚本，审查断链、缺口、潜在冲突和三性状态。
6. 交由执业律师逐项确认证明目的、三性、举证责任和诉讼策略。

输入字段、状态和关系规则见 [references/evidence-map-contract.md](references/evidence-map-contract.md)；审查边界和缺口分类见 [references/review-boundaries.md](references/review-boundaries.md)。

## 生成报告

~~~bash
python scripts/build_evidence_map.py \
  examples/evidence-map.example.json \
  --output /path/to/new-evidence-map
~~~

输出目录必须不存在。脚本原子性生成：

- evidence-map.json：机器可读关系、缺口、冲突和审查状态；
- evidence-matrix.csv：按证据排列的事实、争点、诉请或抗辩覆盖矩阵；
- 证据映射报告.md：供律师复核的中文报告；
- validation.json：结构和引用完整性检查结果。

## 质量门禁

- 任一编号引用不存在的实体时阻断输出。
- 任一来源定位缺少引文或页码、段落、字符位置时阻断输出。
- 证明目的没有原文依据或用户确认记录时阻断输出。
- 三性被标记为 accepted 或 disputed 但缺少人工确认记录时阻断输出。
- 含有庭审、开庭或法庭录音来源时阻断输出，不执行转写或内容提取。
- 输出状态固定为 lawyer_review_required；脚本不得设为 lawyer_reviewed。

## 禁止事项

- 不根据文件名、证据类型或常识自动生成证明目的。
- 不将“已收集”“已解析”或“机检通过”等同于三性成立。
- 不自动判定证据能否达到证明标准、证明责任是否完成或案件胜败。
- 不修改原始证据，不自动签名、盖章、发送或提交。
