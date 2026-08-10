---
name: cn-negotiation
description: 将中国律师谈判事项整理为严格隔离的内部策略工作簿与对外预览，处理议题优先级、客户授权、底线、BATNA、方案评分、让步交换、会议纪要与待确认项。在诉前、诉中、仲裁、执行、合同或其他法律实务中准备商务或争议谈判时使用；不用于替客户承诺、操纵或欺骗对方、自动发送、签署或对外披露。
---

# 中国律师谈判安全工作台

## 执行流程

1. 将内部目标、客户授权、底线、BATNA、议题优先级与内部评分只写入 `internal_strategy`。
2. 将可披露议题、提案、条件式让步交换、会议纪要和待确认项只写入 `external_workspace`。
3. 按 [references/input-output-contract.md](references/input-output-contract.md) 组织输入，并按 [references/safety-boundaries.md](references/safety-boundaries.md) 完成披露复核。
4. 从项目根目录使用 `.venv` 运行：

   ```bash
   python skills/cn-negotiation/scripts/build_negotiation.py input.json \
     --internal-output negotiation-internal.json \
     --external-output negotiation-external-preview.json
   ```

5. 将内部工作簿仅供律师与获授权团队审查；对外预览仍须由执业律师逐项复核，不得因脚本生成而视为已获客户授权。

## 隔离规则

- 脚本从白名单对外字段重建独立预览，不复制 `internal_strategy` 对象。
- 对外预览禁止出现内部底线、授权上限或下限、BATNA、内部目标、优先级、评分和内部备注。
- 对已知内部短语、授权金额和敏感标记执行字面泄露检查；检测到泄露即阻断全部输出。
- 字面检查不能识别所有语义改写，因此输入必须有律师披露复核确认，输出状态仍固定为 `lawyer_review_required`。

## 谈判边界

- 让步必须表达为“给予什么、换取什么、在何条件下生效”，不生成无条件承诺。
- 方案评分只按律师明示输入的标准、权重和分值计算，不自动排名、推荐或预测结果。
- 会议纪要中的“暂定”不等于“已承诺”；所有 `pending` 项必须进入待确认清单。
- 不虚构权限、时限、证据、第三方报价或其他事实；不使用欺骗、威胁或不当操纵策略。
- 不自动发送、签署、盖章、提交或对外发布任何输出。

## 必须阻断

- 客户授权未明示确认，或披露复核未完成。
- 内外部编号引用断裂、评估标准权重不等于 100，或方案评分不完整。
- 对外文本命中敏感标记、已知内部短语或授权金额。
- 提案或纪要将内容标记为已接受、已承诺或可直接发送。
- 任一输出已存在、输入与输出路径相同，或两个输出路径相同。

## 输出门禁

- 内部工作簿标记 `internal_only: true`和 `external_use_permitted: false`。
- 对外预览仅包含议程、待审提案、条件式交换、会议纪要和待确认项，不包含任何内部策略字段。
- 两份输出的 `artifact_state` 均固定为 `lawyer_review_required`，所有发送、签署、提交和承诺控制均固定为 `false`。
- 输出采用临时文件与硬链接原子新建；任一路径存在时拒绝覆盖。
