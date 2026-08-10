# 合同审查输入输出契约

## 条款覆盖与内部结构

逐条审查之外，可登记 `coverage_requirements`、`defined_terms` 和 `cross_references`：

- 条款覆盖项必须来自当事人需求、已核验法源或已确认的交易清单，不得因合同类型自动套用所谓“通用必备条款”。
- `matched_clause_ids` 只记已人工确认或有可回查原文定位的匹配；未确认适用性时使用 `unconfirmed`。
- 法律类覆盖项的适用性已确认时，必须引用已核验的法源编号。
- 定义词台账区分“已定义未使用”和“已使用未定义”，不自动修改原文。
- 交叉引用台账记录修改、条件、优先、并入和冲突关系；目标无法回查时保留为问题。

缺失项中的 `recommendation` 只是起草方向，输出固定标记为未应用，不得静默插入合同。

## 源文保全

1. 先将待审版本确定性导出为 UTF-8 纯文本快照。
2. 以快照文件的原始字节计算 `source_contract.sha256`。
3. 条款的 `start_char` 包含、`end_char` 不包含；两者是快照解码后的 Python 字符索引。
4. `original_text` 必须与源文该区间逐字相同。脚本输出原文及条款 SHA-256，不修正标点、空格或换行。

## 意见结构

- `issue`：可复核的问题描述，不得写成未经裁判的确定无效结论。
- `risk`：使用高、中、低级别，表述状态只能为 `potential` 或 `needs_verification`。
- `source_refs`：至少引用对应条款 ID 或其他已识别材料。
- `authority_ids`：法律类问题至少引用一个已核验法源；商业或起草问题可为空。
- `suggestion`：作为独立建议保存，不覆写原文。
- `delta`：仅是待人工采纳的变更指令。`replace` 与 `delete` 必须指定原文中逐字存在的 `target_text`；`replace` 还必须指定 `proposed_text`。

## 结果解释

- `blocked=true`：存在授权、版本、源文完整性、法源或表述风险门禁，不得对外使用。
- `review_items`：保留每个原条款与其意见列表，没有意见的条款仍保留。
- `redline_instructions`：是指令副本，不表示已修改或已接受。
- `artifact_state`：始终为 `lawyer_review_required`。
