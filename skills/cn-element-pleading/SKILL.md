---
name: cn-element-pleading
description: 将中国民事传统叙述式起诉状转换为可核验的要素式起诉状。用于民间借贷、离婚、买卖合同、机动车交通事故责任纠纷；保留原诉讼请求与事实原文，逐项标注来源，缺失字段明确留空，并输出带固定作者属性的 DOCX 转换稿和核验记录。
---

# 传统诉状转要素式诉状

## 定位

本 Skill 的默认且唯一主路径是“已有传统起诉状→要素式转换”。从零起草传统起诉状不在本 Skill 内完成，应交给独立的起诉状起草 Skill。

要素式示范文本是诉讼便利工具，不是立案强制前提。法〔2025〕82号要求“积极引导、尊重选择”，不得以强制使用示范文本为由有案不立。

当前确定性支持四类：

- 民间借贷纠纷；
- 离婚纠纷；
- 买卖合同纠纷；
- 机动车交通事故责任纠纷。

案由不在上述范围，或规则识别结果为低置信度时，停止自动转换并请用户或承办律师确认。不得回退到另一案由模板。

## 转换边界

转换只做“切分、摘录、归位、标记”，不做改写、补写或法律评价：

1. 原诉讼请求保持原顺序和原文字面，不擅自增减请求、金额或责任主体。
2. 每个已填写要素必须带原文摘录；摘录须能在源文中唯一定位或带准确字符位置。
3. 原文未提供的项目标记为“missing”，正式内容栏保持空白，只在核验报告中显示缺失状态；与案件明显无关的项目只有在原文足以支持时才能标记为“not_applicable”。
4. 识别不确定、前后矛盾、同一字段存在多个候选值时标记为“conflict”，交由人工处理。
5. 不计算利息、损失、诉讼费，不替用户选择调解、保全、鉴定或授权事项。
6. 不自动签名、盖章、提交法院或发送给对方当事人。

## 执行流程

### 1. 准备源快照和映射骨架

接受 `.txt`、`.md`、`.docx`；扫描版 PDF 或图片应先经合规 OCR 转为可核验文本。

```bash
python scripts/convert.py prepare \
  --input /path/to/traditional-complaint.docx \
  --output /path/to/new-work-directory
```

如案由已由律师确认，可显式指定：

```bash
python scripts/convert.py prepare \
  --input /path/to/traditional-complaint.docx \
  --case-type private_lending \
  --output /path/to/new-work-directory
```

该步骤生成：

- `source-snapshot.json`：规范化原文、哈希、章节和诉讼请求；
- `element-mapping.json`：按案由生成的全量要素骨架；
- `prepare-report.json`：规则识别得分和待人工确认事项。

### 2. 仅用原文摘录填写映射

编辑 `element-mapping.json`。每个要素使用以下状态之一：

- `provided`：`value` 与 `source_quote` 必须是同一段原文；
- `missing`：原文未提供，值和摘录均为空；
- `not_applicable`：原文明确表明不适用，仍须给出原文摘录；
- `conflict`：原文存在冲突或多个无法取舍的表述，保留候选原文并人工复核。

案由经用户或承办律师确认后，才可把 `case_type_human_confirmed` 设为 `true`。人工智能不得仅凭自身分类结果代替该确认。

字段目录见 `configs/element-fields.json`，数据契约见 `references/conversion-contract.md`。不得把模型推断结果伪装成原文信息。

### 3. 验证来源

```bash
python scripts/convert.py validate \
  --snapshot /path/to/work/source-snapshot.json \
  --mapping /path/to/work/element-mapping.json
```

验证器检查源文件哈希、案由、字段全集、摘录字符位置、诉讼请求逐字一致、状态和值的组合以及未映射原文。任一错误均不得生成交付稿。

### 4. 生成 DOCX

```bash
python scripts/convert.py build \
  --snapshot /path/to/work/source-snapshot.json \
  --mapping /path/to/work/element-mapping.json \
  --output /path/to/new-output-directory
```

输出包括：

- `要素式民事起诉状-转换稿.docx`：表格化转换稿；
- `转换核验报告.json`：源哈希、映射统计、错误与警告；
- `generation-manifest.json`：生成器版本、输出哈希、作者属性。

DOCX 作者与最后修改者必须为 `AIOffice职场通关-excel1949`。生成器使用独立、通用的核验稿式样，不冒充最高人民法院原版表格；如法院要求原版示范文本，律师应将核验后的内容人工转录至相应官方文本。

## 质量门禁

交付前必须：

1. 运行 `validate` 且错误为零；
2. 确认案由由承办律师确认，不仅依赖关键词分类；
3. 逐项核对当事人、诉讼请求、金额、日期、证据和管辖法院；
4. 检查所有 `missing`、`conflict` 和未映射原文；
5. 渲染 DOCX 为逐页图片，检查表格、分页、字体和中文标点；
6. 根据法〔2025〕82号官方版本和受理法院最新要求进行最终人工转录或调整；
7. 由执业律师逐案审查并确认。

## 参考边界

- `references/法〔2025〕82号-67类示范文本-最高法官方.md` 是当前规则核对基线（2026-08 经 MinerU 由官方 PDF 转写，转换记录与溯源见 `references/source-provenance.md`）。
- 已废止的法〔2024〕46号旧版 DOCX 不进入公开 Skill；旧版取证只保留在原教学目录的内部审计记录中，生成流程不得依赖。
- 不运行、下载或复制安全性与许可证不明的第三方转换器；只可抽象借鉴“中间结构、区域边界、精确勾选、输出核验”等方法。

## 对外使用提示

1. AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。
2. 使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。
3. AI 不能替代律师对案件具体情况进行独立法律判断。
4. 本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。
5. AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。
