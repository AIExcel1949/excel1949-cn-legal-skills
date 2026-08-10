# 总路由与编排数据契约

`track` 只能由用户或律师确认，可取 `dispute`、`transaction`、`compliance`、`mixed` 或 `unknown`。`mixed_tracks` 只在混合事项中使用。

`requested_outputs` 必须逐项保留用户明确要求的交付物名称。`delivery_format` 可取 `source_native` 或 `docx`；未提供时使用各 Skill 的原生产物。交付物只按 `deliverable-registry.json` 映射，不根据名称相似度猜测生成器。未提供 `runtime_profile` 时默认使用 `codex_app`。

路由器生成：

- `case_root`：固定案件输出根目录；
- `requested_deliverables`：交付物、来源 Skill、登记生成器、模板标识、预期文件和支持状态；
- `execution_steps`：带依赖关系的执行清单；每一步同时锁定执行者类型、唯一可写目录和获准交付物或模板；
- `role_id`、`role_mode` 与 `spawn_policy`：锁定专家角色、单次工作模式和创建时机；
- `selected_skills`：本次专家任务允许加载的最小 Skill 子集，不等于该角色的全部能力；
- `required_gates_before` 与 `produced_gates`：记录执行前置门禁和本步骤完成的门禁；
- `independence_group`：区分总控、法源、事实、起草和独立审校，禁止起草者自审；
- `role_prompt_sha256`：锁定当前专家提示词，防止运行中静默更换角色职责；
- `runtime_profile`：`codex_app`、`claude_code`、`openclaw` 或 `portable_serial`；
- `orchestration_mode`：Codex App 默认为动态专家团，其他环境使用对应专家机制；
- `fallback_mode`：固定为 `serial_same_plan`，后备执行不得改变计划；
- `control_owner`：固定为 `cn-legal`，表示下游无权自行变更交付契约；
- `plan_sha256`：执行清单哈希，防止下游静默改变目标；
- `deliverable_registry_sha256` 与 `procedure_template_manifest_sha256`：锁定交付登记表和程序文书模板清单；
- `expert_registry_sha256` 与 `quality_gates_sha256`：锁定专家登记表和 G0—G7 质量门禁；
- `blockers`：未确认轨道、未登记交付物、授权委托书尚未分型或尚无专用 DOCX 生成器等阻断项。

主路由不分析案情文本，不自行作实体法律判断。`blocked=true` 时不得调用下游生成替代品。`artifact_state` 固定为 `lawyer_review_required`；路由计划本身不表示任何下游工作已经执行。

执行图至少包含：收案与共享核心 → 法源核验；争议事项另加事实证据分析；随后才进入专业子路由和生成；最后由不同 `independence_group` 的独立审校专家逐件终检，再由案件总控执行交付审计。宿主无法创建子代理时，主代理按相同角色顺序串行执行，不得跳过门禁。

最终验收按文书逐份覆盖。每份 DOCX 必须对应一个独立 `cn-verify/<artifact-id>/review-report.json`，其 `input_sha256` 与原 DOCX 完全一致，状态不得为 `blocked`，且同目录存在 `review-report.md`。只有目录中出现报告文件而没有哈希覆盖，不视为终检完成。
