---
name: cn-law-update
description: 对中国法律法规、司法解释、规章、规范性文件、文书模板和旧法律结论进行新旧版本比对、影响识别与人工复核门禁。用于法律更新监测、旧模板排查、Skill 依赖检查、旧意见有效性复核或生成可审计变更报告时使用；不用于自动改写、覆盖或发布生产模板。
---

# 中国法律更新影响分析

## 执行流程

1. 确定比对对象、新旧版本、比对日和受监测的 Skill、模板、检查表或旧结论。
2. 先用宿主已配置的官方网页、MCP 或自有数据库检索旧版、现行版和修改线索；检索结果只作候选基线，不能单独证明现行效力。
3. 按 [references/source-policy.md](references/source-policy.md) 核验发布机关、文号、效力状态、施行日期、核验日期和官方原文。网页标题、搜索摘要和政策解读不得充当规则原文。
4. 将可定位原文整理为 `old_version.units` 和 `new_version.units`，每个单元保留稳定 `unit_id`、条款定位和原文。
5. 按 [schemas/law-update-input.schema.json](schemas/law-update-input.schema.json) 准备 JSON；输出契约见 [schemas/law-update-report.schema.json](schemas/law-update-report.schema.json)。从项目根目录使用 `.venv` 运行，首次使用先按根目录 `requirements.txt` 安装 `jsonschema` 等依赖：

   ```bash
   python scripts/validate_update.py input.json
   ```

6. 生成确定性差异、受影响清单和门禁结果：

   ```bash
   python scripts/build_report.py input.json --output output/change-report
   ```

7. 按 [references/change-taxonomy.md](references/change-taxonomy.md) 复核法律变更类型和影响等级，再按 [references/review-gate.md](references/review-gate.md) 完成执业律师人工审批。

## 输入约束

- 使用官方全文、官方附件或经校验的官方扫描原件；保留可回查 URL 和 SHA-256。
- 区分“文本差异”“程序命中的影响候选”与“律师确认的法律影响”。
- 将直接依赖记录在 `uses_unit_ids`，关键词仅用于生成待复核线索，不作为法律结论。
- 脱敏示例只能使用 `training_fixture` 模式，不得冒充真实法源。

## 阻断条件

出现下列任一情形时，将报告标记为 `blocked` 或 `training_only`：

- 缺少官方原文、效力状态、核验日期或可回查来源；
- SHA-256 与录入原文不一致；
- 将网页标题、摘要或解读文章当作法律原文；
- 新版本效力不明，或新旧版本无法唯一定位；
- 人工复核人、时间、结论或门禁清单不完整。

## 产出和边界

- 输出 `change-report.json` 和 `change-report.md`，包含变更记录、受影响 Skill/模板/旧结论、来源问题和人工门禁。
- 输出目录必须不存在；脚本先在同一文件系统的临时目录写入，完成后原子更名。
- 任何门禁状态都不会修改、覆盖、发布或删除生产 Skill 和模板。
- `approved_for_manual_update` 仅表示允许另行人工编辑，不表示生产文件已被改动。

## 对外使用提示

1. AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。
2. 使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。
3. AI 不能替代律师对案件具体情况进行独立法律判断。
4. 本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。
5. AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。
