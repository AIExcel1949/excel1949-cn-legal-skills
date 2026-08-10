---
name: cn-intake
description: 将中国律师初次咨询、收案访谈、当事人陈述和材料目录整理为可追溯的案件初始数据、访谈提纲、信息缺口与风控门禁。用于民事、商事、刑事、行政、仲裁、执行和非诉事项的首次接洽或补充访谈；不自动判断案由、利益冲突、诉讼时效、是否承办或收费方案。
---

# 中国律师收案访谈

## 执行流程

1. 把用户原始诉求、期望结果和紧急程度分开记录，不先改写为法律结论。
2. 为参与人、材料和陈述分配稳定编号；每项事实保留状态与来源定位。
3. PDF、DOCX、扫描件或长文本进入事实台账前，按 [references/extraction-integrity.md](references/extraction-integrity.md) 核验解析完整性；检索未命中时，不得直接断言原文没有。
4. 将姓名、日期、金额、程序阶段等冲突标为 `conflict`，不得选择模型认为更可信的一项。
5. 分别记录利益冲突、身份核验、期限风险、紧急措施和委托手续的人工审查状态。
6. 运行确定性脚本生成收案摘要、缺失事项和访谈问题。从项目根目录使用 `.venv` 运行；首次使用先按根目录 `requirements.txt` 安装 `jsonschema` 等依赖：

```bash
python scripts/prepare_intake.py examples/intake.example.json --output /path/to/new-intake-output
```

解析完整性审计命令：

```bash
python scripts/audit_extraction.py \
  /path/to/extraction-audit-input.json \
  --source-file /path/to/original-file \
  --output-dir /path/to/new-extraction-audit
```

7. 将输出交律师决定是否补访、核验或承办，不把 `ready_for_lawyer_decision` 解释为已经承办。

输入字段、状态和阻断规则见 [references/intake-contract.md](references/intake-contract.md)。

## 阻断条件

- 输入包含真实案件材料但没有脱敏或授权处理说明；
- `matter_id`、参与人编号、材料编号或陈述编号重复；
- 已确认事实没有任何来源定位或确认说明；
- 利益冲突状态为 `blocked`，或关键风控状态尚未完成；
- 用户要求自动决定承办、收费、特别授权、风险代理或诉讼策略。

## 输出门禁

- 事实、当事人原话、模型归纳和律师判断必须分层；
- 缺失信息保留为缺失，不填“无”或“不适用”；
- 访谈问题只用于补足事实，不暗示特定答案；
- 输出状态最高为 `ready_for_lawyer_decision`，不得写成“审查通过”或“已承办”；
- 所有文件写入新目录，不覆盖用户输入。
