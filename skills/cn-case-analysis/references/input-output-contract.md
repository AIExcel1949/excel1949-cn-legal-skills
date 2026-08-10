# 输入输出契约

## 输入

`schemas/analysis-input.schema.json` 使用绝对 `$id` 引用 `cn-legal-core` 的 party、claim、fact-ledger、issue、evidence 和 authority Schema。运行脚本会从相邻 Skill 加载这些 Schema，不通过网络解析。

`issue_analyses` 与 `issues` 必须一一对应。前者只增加分析框架、父子关系、各方主张、要件、风险和研究任务，不改写核心争点。

## 引用完整性

脚本会确定性检查：

- 所有编号在各自集合内唯一；
- 争点父节点存在且不构成环；
- 请求、事实、证据、法源和当事人指针存在；
- 核心争点的 `element_ids` 与分析要件一致；
- 已提供的律师判断包含复核人和时间。

## 输出

新目录内固定生成：

| 文件 | 用途 |
| --- | --- |
| `analysis.normalized.json` | 通过 Schema 与交叉引用检查的原始输入 |
| `analysis-derived.json` | 编排后的争点树、要件矩阵、缺口与人工判断区 |
| `validation.json` | 错误、警告与引用完整性结果 |
| `案件中立分析报告.md` | 供律师复核的中立阅读稿 |

生成器先写入同父目录的临时目录，全部成功后才原子改名。目标已存在时直接失败。
