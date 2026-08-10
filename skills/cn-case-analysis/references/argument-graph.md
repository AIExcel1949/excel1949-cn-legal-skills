# 可回查法律论证图

当需要把要件分析组织为代理词、辩护词、法律意见或对抗性分析时，建立独立论证图，不把流畅文本当作论证完整的证明。

## 节点与关系

- 节点区分事实前提、规则、推理、结论、反对意见、回应和竞争性假设。
- 关系区分支持、攻击、限定、依赖和击破。支持、限定和依赖关系必须构成无环图。
- 每个节点引用现有争点、事实、证据和法源编号，不能用散文隐藏断链。
- `ai_proposed` 与 `lawyer_confirmed` 分开。脚本只报告无支持结论和未回应攻击，不自动选择胜出观点。

## 竞争性假设

材料存在多种解释时，对每个 `alternative_hypothesis` 分别记录支持节点、相反节点、可证伪条件和缺失信息。不以“最佳解释”标签把假设改写为事实。

## 执行

```bash
python scripts/build_argument_graph.py analysis-input.json argument-graph.json --output /path/to/new-argument-graph.json
```

输出固定为 `lawyer_review_required`；置信度只能来自用户声明或律师评估，不得按论据数量、节点数量或固定权重自动打分。
