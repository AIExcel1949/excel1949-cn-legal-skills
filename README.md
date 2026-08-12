# excel1949 中国法律专家团（Claude Code 插件）

**本仓库发布的是「法律专家团」插件**：**40 个法律 Skill + 8 个专家角色**组成的专家团，一队各司其职的法律专家协同办案，非单一助手。它是**独立插件**——不依赖任何特定软件，可独立安装到 Claude Code 等任意 CLI、独立升级、独立使用（安装见下文）；亦可作为「法律 AI 工作台 v1.01 - AIOffice职场通关」（作者：excel1949）的内置专家团运行。

面向中国法律实务，专为法律文书生成与财务数据分析定制：正文排版对齐默认标准（思源宋体、固定行距、纯黑字体、页眉品牌与公众号二维码），**最终交付一律为可编辑 DOCX**。

**版本：v1.0.0**

## 学习资源

- **飞书知识库**（免费法律 AI 视频课程、配套资料、更新说明）：[https://excel1949.feishu.cn/wiki/Xs6gwUrbsi6Wcak804ocUG4jnDe](https://excel1949.feishu.cn/wiki/Xs6gwUrbsi6Wcak804ocUG4jnDe)

## 适用平台

- **Claude Code**：官方推荐（安装见下文）；
- **workbuddy、Qoder 等国内 AI 平台**：插件/Skill 格式兼容，可直接安装使用；
- 其他兼容 Claude Code 插件生态的 CLI 与工具均可安装。

## 藏经阁架构（Scripture Vault Architecture）

本专家团采用**「藏经阁架构」**——一种原创的法律 AI 插件设计（2026-08 定名）：

- **知识库外置，如藏经阁**：18 个领域知识包（`domain-packs/`，含案由证据问题族、官方法源索引）独立于 Skill 存放，按案由经 `domain-pack-routing` 路由，执行计划生成时全文注入（`domain_guidance`）——招式在外，心法在阁；
- **技能轻装，如江湖招式**：40 个 Skill 只承载"怎么生成"的确定性流程（收案→法源核验→事实证据→起草→渲染→终检），内部不囤积知识，法源一律运行时经宿主检索核验（`cn-research` 逐项可回查）——不随附法律文本，永不因版本过期而失真；
- **按需取经，如临敌翻谱**：每个案件只注入与案由匹配的领域包，知识粒度对应当案争点，不冗余、不串味；
- **确定性收口**：全部文书走登记生成器/渲染器/独立终检/交付审计，机器可复核、可追溯。

此架构将"知识"与"技能"彻底解耦：知识更新只改 `domain-packs/`，技能迭代只动 `skills/`，互不牵连——是为「藏经阁」。

## 安装（已验证：claude CLI 2.1.223 实测通过）

```bash
# 1. 添加市场（git URL 或本地路径均可）
claude plugin marketplace add https://github.com/AIExcel1949/excel1949-cn-legal-skills
# 2. 安装插件
claude plugin install excel1949-cn-legal-skills@excel1949-cn-legal-marketplace
```

安装后在 Claude Code 中输入 `/excel1949-cn-lawyer-skills:cn-legal` 启动总路由。

## Skill 功能总览（40 个）

### 核心编排与基础设施

| Skill | 功能 |
|---|---|
| `cn-legal` | 主路由：识别任务类型，生成可审计执行计划（含领域包硬注入、渲染/打包/交付收口） |
| `cn-legal-core` | 案件工作区创建、DOCX 品牌化（页眉页脚统一标准）、OOXML 安全审计 |
| `cn-matter` | 案件生命周期状态流转与任务清单 |
| `cn-intake` | 收案访谈、信息缺口与风控门禁 |
| `cn-research` | 法源检索核验（法规/司法解释/案例库，逐项可回查） |
| `cn-verify` | 文书终检（事实/证据/法源/引文/内部一致性，逐份 review-report） |
| `cn-timeline` | 事实与程序时间轴（日期精度与冲突识别） |
| `cn-deadline` | 期限确定性计算与审计（工作日历） |
| `cn-calc` | 本金/利息/违约金等确定性计算（含中文大写） |
| `cn-law-update` | 新旧法律版本比对与影响识别 |

### 诉讼争议（民事/执行）

| Skill | 功能 |
|---|---|
| `cn-complaint` | 民事起诉状 **DOCX**（渲染器：标题 18pt 加粗、思源宋体、固定行距、案由、事实与理由连续） |
| `cn-defense` | 答辩矩阵与答辩状 **DOCX** |
| `cn-dispute` | 民商事争议请求分流 |
| `cn-element-pleading` | 传统诉状转要素式诉状（四类案由，可核验） |
| `cn-case-analysis` | 争点树、要件矩阵中立分析（报告 **DOCX**） |
| `cn-enforcement` | 执行案件材料整理（执行依据/财产线索/措施） |
| `cn-appeal` | 上诉审查与上诉状 **DOCX** |
| `cn-arbitration` | 仲裁材料（协议/机构/管辖异议/仲裁员披露） |
| `cn-mediation` | 调解谈判材料与协议条款清单 |

### 文书生成（程序文书/申请书/函件）

| Skill | 功能 |
|---|---|
| `cn-procedure` | 程序文书批量生成：所函、授权委托书、委托代理合同、审批表、保全/执行申请书（41+ 份品牌 DOCX 模板，全部统一品牌化） |
| `cn-applications` | 程序申请工作底稿（保全/查证/鉴定/延期/回避等路由，DOCX 渲染） |
| `cn-legal-letter` | 律师函 **DOCX**（可追溯来源与法源核验） |
| `cn-legal-opinion` | 法律意见书（正反分析、条件性结论） |
| `cn-evidence-catalog` | **证据目录 3 格式**（证据清单横列表/标准竖表/叙述式）DOCX，`--format` 选择；叙述式为默认（法院要求），表格版备选 |

### 证据

| Skill | 功能 |
|---|---|
| `cn-evidence` | 录音转写（5 种 ASR 后端、声纹聚类、人工校核） |
| `cn-evidence-map` | 证据—待证事实—争点—诉请映射与缺口分析（→ 证据目录渲染链路） |

### 非诉交易

| Skill | 功能 |
|---|---|
| `cn-contract-draft` | 合同结构化起草（条款/风险分配/法源记录，**DOCX**） |
| `cn-contract-review` | 合同审查（逐字快照+哈希，issue/risk/source/authority/suggestion 报告 **DOCX**） |
| `cn-diligence` | 法律尽调（数据室/事实发现/红旗/例外） |
| `cn-negotiation` | 谈判工作簿（内部策略与对外预览严格隔离） |
| `cn-company` | 公司治理材料整理（章程/股东/决议） |
| `cn-ma` | 并购交易（先决条件/陈述保证/赔偿/交割） |
| `cn-transaction` | 非诉任务分流 |

### 合规

| Skill | 功能 |
|---|---|
| `cn-compliance` | 综合合规审查分流 |
| `cn-compliance-review` | 合规差距/风险分级/整改建议 |
| `cn-data-privacy` | 个人信息与数据合规审查（盘点/告知同意/跨境） |
| `cn-employment` | 劳动用工全周期审查 |

### 刑事/行政

| Skill | 功能 |
|---|---|
| `cn-criminal-defense` | 刑事辩护阶段材料（要件候选/证据合法性/程序） |
| `cn-admin-litigation` | 行政诉讼材料（行政行为/复议前置/起诉期限） |

## 专家角色（8 个）

| 角色 | 职责 |
|---|---|
| `matter-lead` | 案件总控（唯一常驻，Task 派发任务包，交付审计） |
| `source-counsel` | 法源核验（法规/案例/版本/时点） |
| `fact-evidence-analyst` | 事实证据（时间轴/证据映射/金额期限） |
| `civil-dispute-counsel` | 民商事争议（诉辩/程序/庭审/调解/上诉/执行） |
| `special-proceedings-counsel` | 特殊程序（仲裁/刑事/行政三选一） |
| `transaction-counsel` | 交易非诉（合同/尽调/意见/函件/并购） |
| `compliance-counsel` | 企业合规（综合/劳动/数据三选一） |
| `independent-reviewer` | 独立终检（fresh context，与起草者隔离） |

## 交付标准

1. **全部正式文书为 DOCX**（起诉状/答辩状/代理词/证据目录/保全/上诉/执行/授权委托/委托代理合同/合同等），禁止 MD/JSON 底稿当作交付物；
2. **单一交付包** `delivery/`，中文序号分类目录（`01-民事起诉状/`、`02-证据目录/`…），无中间产物；
3. **统一格式**：标题 18pt 居中加粗（证据目录 22pt）、标题与正文不空行（段后间距 30pt）、页眉 Logo 左上 + 二维码右上、页脚仅页码、孤行控制、思源宋体（OFL 免费商用）；
4. **独立终检**：每份 DOCX 走 `cn-verify`（input_sha256 一致、blocker=0），交付审计硬检查 DOCX 成品覆盖；
5. 案件根目录收纳：`delivery/`（成品）+ `workspace/`（全部中间产物）+ `交付说明.md`。

## 目录结构

```
├── .claude-plugin/          # plugin.json + marketplace.json（安装入口）
├── agents/                  # 8 个专家角色定义
├── skills/                  # 40 个法律 Skill（含生成器/渲染器/模板/校验）
├── assets/                  # 品牌资源（页眉 Logo、公众号二维码 wechat-qr.jpg、字体）
├── domain-packs/            # 18 个领域业务包（PACK.md 案由证据脚手架）
└── LICENSE / NOTICE / TRADEMARKS.md
```

## 配套软件（欢迎下载）

**「法律 AI 工作台 v1.01 - AIOffice职场通关」**（作者：excel1949）——以本专家团为核心能力的**法律 AI 工作台软件**：软件内可运行终端、内置文书工作区、一键编排专家团协同办案，专为法律文书生成与财务数据分析打造。**软件将在独立仓库发布，欢迎届时下载使用**（下载地址发布后将于本文档更新）。

## 运行环境与能力定位

- **插件独立性**：本插件可独立安装到 Claude Code、workbuddy、Qoder 等 CLI 使用（安装见上文），亦可作为上述「法律 AI 工作台」软件的配套专家团协同运行——软件与插件解耦，各自独立发布、独立升级。
- **能力定位**：「法律 AI 工作台」软件连同本专家团，是**面向法律实务的领域专精 AI**——以**法律文书全流程生成**为核心（收案、法源核验、事实证据分析、起诉状/答辩状/代理词/合同/法律意见等确定性 DOCX 交付、金额期限计算、独立终检），并在此基础上提供**部分财务数据分析**能力。因领域专精定位，**编程开发、系统运维等通用工程能力弱于通用智能体**——此为设计取舍（专业领域深度优先，通用任务交给通用模型），请按领域专长使用。

## 使用边界

1. AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人；
2. 使用前必须由专业执业律师人工核验事实与法律适用（全部产物状态 `lawyer_review_required`）；
3. 本集群不随附法律文本，法源统一经宿主已配置的官方网页、MCP 或自有数据库检索；
4. 许可协议见 `LICENSE`（GNU GPL-3.0），品牌使用边界见 `TRADEMARKS.md`。
