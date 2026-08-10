---
name: cn-legal
description: 识别中国律师工作请求属于争议解决、交易非诉、企业合规或混合事项，生成并控制可审计的 Skill 执行清单、子路由、交付物、输出目录和最终门禁。用于用户尚未明确应调用哪个法律 Skill、任务跨多个工作流、要求多份文书或需要建立总办案链路时；不替律师选择诉讼策略，不允许下游绕过登记生成器或直接交付。
---

# 中国律师总路由

## 总负责人规则

`cn-legal` 是完整任务的唯一总负责人，不把“已列出下游 Skill”误认为任务已经完成。

1. 必须逐项保留用户明确要求的 `requested_outputs`，并读取 `references/deliverable-registry.json` 映射来源 Skill、生成器、模板和原生产物。
2. 开始编排前读取 `references/expert-registry.json`、`references/quality-gates.json` 和所选角色的提示文件。39 个 Skill 只映射为 8 个角色族，不得创建“一 Skill 一专家”；除 `matter-lead` 外均按阶段创建。
3. 必须把项目根目录与 Skill 安装目录分开。案件产物默认写入 `<PROJECT_ROOT>/output/cases/<task-id>/`；任何子路由和子任务都不得写入 Skill 目录。
4. 默认运行环境为 Codex App。Codex App 提供动态子代理能力时，必须按执行清单把彼此独立的子路由、生成任务和终检任务派发给登记专家；不得因使用子代理而转移总负责人身份。Claude Code 插件使用预声明专家，OpenClaw 使用其可用的运行时专家；确无子代理能力时，才由主代理按同一清单串行执行。
5. 无论并行还是串行，控制权均留在 `cn-legal`：下游产物必须返回主路由核对文件集合、来源模板或生成器、哈希、DOCX 品牌、终检报告和阻断项。
6. 用户明确要求扩张文书集合时应当扩张，但每份文书必须路由到对应 Skill。不得把所有 Markdown 用同一个通用转换器批量改成 DOCX。
7. 登记表显示 `docx_supported=false` 时，不得临时使用空白 `python-docx`、Pandoc 或 Markdown 转 Word 冒充正式文书；执行计划必须阻断并明确指出缺少专用 DOCX 生成器。
8. 泛称“授权委托书”不能唯一确定模板。必须先确认自然人委托律师、自然人委托近亲属，还是法人或非法人组织委托本单位工作人员；未确认时保持阻断。

## 执行流程

1. 先识别法域、案件阶段、目标交付物和是否存在紧急期限、人身安全、财产保全或敏感信息风险。
2. 只有用户或律师明确确认 `track` 后才路由；不从简短案情自动认定争议性质。
3. 争议事项交给 `cn-dispute`，交易非诉交给 `cn-transaction`，企业合规交给 `cn-compliance`；混合事项分成彼此独立的工作流。
4. 所有链路先经过 `cn-intake` 和 `cn-legal-core`，法源问题经过 `cn-research`，最终交付前经过 `cn-verify` 与主路由交付审计。
5. 运行确定性路由器。`--project-root` 和 `--output` 必须使用 Skill 目录之外的绝对路径：

```bash
python <SKILL_ROOT>/scripts/route.py \
  <PROJECT_ROOT>/matter-data/route-input.json \
  --project-root <PROJECT_ROOT> \
  --output <PROJECT_ROOT>/output/cases/<task-id>/00-route-plan.json
```

字段和状态见 [references/routing-contract.md](references/routing-contract.md)。

6. 检查 `requested_deliverables`。只执行 `status=ready` 的项目；任一 `docx_not_supported:*`、`unsupported_requested_output:*` 或人工门禁阻断项存在时，不得生成替代品。
7. 按 `execution_steps` 的依赖关系调度。Codex App 默认执行 `executor=dynamic_subagent` 的步骤；每个专家只能写入 `allowed_write_root`，只能制作 `authorized_deliverable_ids` 和 `authorized_template_ids`。子路由不能删除用户交付物、改写目标格式或更换输出根目录。
8. 任务包同时锁定 `role_id`、`role_mode`、`selected_skills`、`required_gates_before`、`independence_group` 和 `role_prompt_sha256`。专家不得加载未选 Skill、跳过前置门禁或把工作交给未登记角色。
9. 全部下游返回后，由主路由逐项比对执行计划与实际文件；任何未登记文件、缺失文件或通用转换 DOCX 均视为未完成。每份 DOCX 必须在 `cn-verify/<artifact-id>/` 下具有独立的 `review-report.json` 与 `review-report.md`，报告中的 `input_sha256` 必须与该 DOCX 一致且 blocker 为零。

## 人工门禁

- 不确认利益冲突、委托权限、收费、用章、发送、提交或承办。
- `track=unknown` 或 `track_status!=user_confirmed` 时输出阻断项，不调用下游。
- 紧急风险只生成升级提醒，不自行计算法定期限或采取外部行动。
- 路由计划不等于法律分析、案件策略或工作已经完成；只有下游产物与主路由终检全部通过后，才能报告机器流程完成。
- 子代理不得自行增加未登记生成器、改用别的模板、改变输出路径、签章、发送或提交。
- 子代理返回“已完成”不等于交付通过。只有 `cn-legal` 主路由运行 `scripts/verify_execution.py` 并生成通过的 `delivery-audit.json` 后，才允许报告机器流程完成。

## Domain Pack Injection

When the input carries `case_cause`, the generated plan includes a `domain_pack` field (see `references/domain-pack-routing.json`). Load `<pack>/PACK.md` from `references/domain-packs/` as the domain question/evidence scaffold for intake, case analysis and evidence mapping steps. The pack is a scaffold only — statutory verification stays with `cn-research`.
