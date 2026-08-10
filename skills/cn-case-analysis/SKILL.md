---
name: cn-case-analysis
description: 将中国诉讼、仲裁、执行、刑事、行政或非诉案件材料按请求权、抗辩和程序问题进行中立结构化分析，生成争点树、要件矩阵、双方主张、风险、待确认与待研究事项。用于阅卷、诉前评估、答辩准备、庭审准备和案件复盘；不自动选择案由，不预测胜诉，不代替律师作最终法律判断。
---

# 中国案件中立分析

## 执行流程

1. 先用 `cn-legal-core` 数据契约登记当事人、请求、事实、证据、争点和法源，不得把推断写成已确认事实。
2. 将争点分别归入 `claim_right`、`defense` 或 `procedure`，再建立父子争点。不得用案由代替争点。
3. 对每个争点逐项记录要件、举证责任、事实指针、证据指针和法源指针。要件状态只是待律师复核的工作标记。
4. 并列呈现各方主张、否认、备位主张和保留意见，不自动采信任何一方。
5. 将事实缺口、证据缺口、法源缺口、程序不确定和策略选择分开列示。律师判断必须保留在独立区域。
6. 如需实体法要件，可记录已加载的 `domain-packs` 标识与版本，但不要复制其实体规则。
7. 运行确定性生成器：

```bash
python scripts/build_analysis.py examples/case-analysis.example.json --output /path/to/new-analysis-output
```

需要把争点、请求、立场、要件、事实、证据和法源展示为只读关系溯源图时，执行：

```bash
python scripts/build_reasoning_graph.py \
  examples/case-analysis.example.json \
  --output /path/to/new-reasoning-graph
```

关系溯源图只展开输入中已经明示的稳定编号关系，不根据语义补造“支持”“反驳”或因果边。节点和边的含义见 [references/reasoning-graph.md](references/reasoning-graph.md)。

分析框架见 [references/analysis-framework.md](references/analysis-framework.md)，输入输出契约见 [references/input-output-contract.md](references/input-output-contract.md)。
需要另行构建支持、攻击、回应或竞争性假设时，读取 [references/argument-graph.md](references/argument-graph.md)，使用对抗论证图工作流，不用自由文本掩盖论证断链。关系溯源图是既有台账的确定性视图；对抗论证图是需单独录入和核验的分析台账，两者不得相互冒充。

## 阻断条件

- 核心对象编号重复、引用不存在或争点树存在环；
- 分析争点与 `cn-legal-core` 争点不能一一对应；
- 要件、当事人主张或风险指向不存在的事实、证据或法源；
- 把未核验法源、待确认事实或模型推断作为已定结论；
- 输出目录已存在，或用户要求脚本自动选择案由、给出最终胜诉结论。

## 输出门禁

- 事实、争议、证据、法源、待确认和律师判断分区输出；
- 争点树同时覆盖请求权、抗辩和程序问题，缺失类型明示提醒；
- 要件矩阵保留举证责任和所有反方意见；
- 案由始终标记为“未由本 Skill 自动选择”，结论始终标记为“待律师独立判断”；
- 输出采用临时目录后原子改名，不覆盖输入或旧结果。
