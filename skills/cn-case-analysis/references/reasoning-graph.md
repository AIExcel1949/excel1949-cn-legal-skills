# 案件关系溯源图

## 一、用途

关系溯源图用于检查争点、请求、当事人立场、构成要件、事实、证据和法源之间是否存在断链。它是案件分析台账的另一种视图，不是胜诉预测、裁判推理、对抗论证或法律知识自动推断系统。

## 二、节点

| 节点类型 | 来源 |
| --- | --- |
| `party`、`claim`、`fact`、`issue`、`evidence`、`authority` | 共享案件数据契约中的对应对象 |
| `position`、`element`、`risk`、`research` | `issue_analyses` 中已登记的分析对象 |

节点标签只用于识别。事实状态、证据三性、法源效力和要件工作状态仍以原始结构化数据为准。

## 三、边

边只表达输入中明示的引用关系：

- `sub_issue_of`：子争点指向父争点；
- `examines_claim`：争点关联请求；
- `position_on`：当事人立场关联争点；
- `stated_by`：立场关联当事人；
- `cites_fact`、`cites_evidence`、`cites_authority`：立场引用相关记录；
- `element_of`：要件属于争点；
- `burden_recorded_for`：要件登记了举证责任主体；
- `linked_fact`、`linked_evidence`、`linked_authority`：要件引用相关记录；
- `risk_on`、`research_for`：风险或研究事项归属于争点。

`cites_*` 和 `linked_*` 不等于法院将采信，也不等于该材料已经证明对应要件。脚本禁止将普通链接改写为“已支持”“已反驳”或“导致”。

## 四、输出

- `reasoning-graph.json`：机器可读节点与边；
- `reasoning-graph.mmd`：只使用 AIOffice 绿系和中性色的 Mermaid 图；
- `validation.json`：输入校验结果。

图中不生成胜诉率、风险概率或自动法律结论。大型案件应按争点筛选后展示，避免把可视化密度误当作证据强度。

如需表达“支持”“攻击”“回应”“竞争性假设”或可证伪条件，必须另行使用 `argument-graph` 工作流，并为新增命题、关系和置信度来源单独承担人工核验责任。
