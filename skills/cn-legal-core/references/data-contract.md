# 统一案件数据契约

## 目录

1. 案件工作区
2. 核心对象
3. 事实状态
4. 文书状态
5. 跨 Skill 规则

## 案件工作区

```text
matter-workspace/
├── matter.json
├── sources/
├── ledgers/
│   ├── facts.json
│   ├── parties.json
│   ├── claims.json
│   ├── issues.json
│   ├── evidence.json
│   ├── authorities.json
│   ├── deadlines.json
│   └── calculations.json
├── drafts/
├── outputs/
└── audit/
```

真实案件材料只进入案件工作区，不进入 Skill、测试或公开仓库。

## 核心对象

| 对象 | 最低要求 |
|---|---|
| matter | 本地事项编号、程序类型、案件阶段、状态 |
| party | 主体类型、程序角色、名称状态、来源 |
| source | 文件名、SHA-256、取得方式、解析状态 |
| fact | 原文值、规范值、来源坐标、状态、确认记录 |
| claim | 原诉请逐字文本、顺序、金额、责任主体 |
| issue | 争点、要件、举证责任、双方主张 |
| evidence | 证据名称、来源、三性、待证事实、核验状态 |
| authority | 法源类型、效力状态、核验日期、官方来源 |
| deadline | 起算事件、规则、期间、截止日、例外 |
| calculation | 输入、公式、步骤、舍入规则、输出 |
| artifact | 输入哈希、模板哈希、输出哈希、审查状态 |
| review | 阻断项、警告、人工确认、确认时间 |

## 事实状态

| 状态 | 含义 | 使用规则 |
|---|---|---|
| `stated` | 原始材料明确记载 | 保留来源后使用 |
| `user_confirmed` | 用户另行确认 | 记录确认时间后使用 |
| `derived` | 计算或法律推导 | 明确标注，不冒充原始事实 |
| `disputed` | 对方否认或存在争议 | 不写成无争议事实 |
| `missing` | 原文未提供 | 留空并进入缺失清单 |
| `conflict` | 多个候选无法取舍 | 阻断关键输出 |
| `unreadable` | OCR 或文件不可可靠识别 | 阻断并人工核对 |

## 文书状态

只允许：

```text
draft
machine_checked
lawyer_review_required
lawyer_reviewed
```

AI 只能写入前三种状态。`lawyer_reviewed` 必须来自律师明确确认并记录时间。

## 跨 Skill 规则

1. 使用稳定 `id` 关联对象，不用姓名、案号或数组位置作为唯一主键。
2. 原文和规范值分开保存，禁止覆盖原文。
3. 每次派生记录算法或规则、时间和输入哈希。
4. 下游不得静默修改上游事实、诉请、证据或法源。
5. 修改必须生成新版本并保留差异记录。

