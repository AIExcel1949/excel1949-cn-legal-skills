---
name: cn-legal-core
description: 为中国法律 Skill 创建和校验统一案件工作区，并提供文件哈希、事实状态、JSON Schema、DOCX 页眉页脚 Logo、作者属性和 OOXML 安全审计。用于新建案件数据、跨 Skill 交换事实、品牌化 Word 模板或生成稿、检查占位符与隐藏作者信息；不用于独立起草法律文书或作实体法律结论。
---

# 中国法律共享核心

## 定位

只执行共享的确定性基础操作，不起草诉状、合同、意见书或诉讼策略。所有上层 Skill 使用同一案件工作区，不在各自目录保存真实案件材料。

## 建立案件工作区

```bash
python scripts/create_workspace.py \
  --matter-id MATTER-2026-0001 \
  --output /path/to/new-matter-workspace
```

输出目录必须不存在。脚本创建 `matter.json`、`sources/`、`ledgers/`、`drafts/`、`outputs/` 和 `audit/`，并把文书状态初始化为 `draft`。

数据字段和状态规则见 [references/data-contract.md](references/data-contract.md)。跨 Skill 传递数据时，不得把缺失值自动改成“无”“不适用”或模型猜测值。

## 品牌化 DOCX

只处理工作副本，不覆盖用户原件：

```bash
python scripts/docx_brand.py \
  /path/to/input.docx \
  /path/to/new-output.docx \
  --title 文书名称 \
  --subject 对应法律任务
```

该脚本统一写入：

- 页眉 AIOffice 真实 Logo；
- 页脚 Logo、AIOffice职场通关和页码；
- 作者与最后修改者 `AIOffice职场通关-excel1949`；
- 分类、公司、主题和人工核验备注。

DOCX 处理边界和阻断规则见 [references/docx-contract.md](references/docx-contract.md)。

## 审计 DOCX

```bash
python scripts/audit_docx.py /path/to/document.docx --json /path/to/audit.json
```

以下任一问题均阻断公开发布：

- 作者或最后修改者不等于统一值；
- 缺少页眉图片、页脚图片、品牌名或页码域；
- 存在批注、修订、宏、OLE、嵌入对象或外部关系；
- 存在未替换占位符、旧作者或来源机构信息；
- DOCX 无法安全打开或 OOXML 路径异常。

## 质量门禁

1. 所有输入文件先计算 SHA-256，不修改原件。
2. 关键字段必须保存来源、状态和人工确认记录。
3. 输出目录不得覆盖，批量任务先写临时目录再提交。
4. 文书生成后重新打开并回读内容和属性。
5. 涉及 DOCX 时完成逐页视觉检查。
6. AI 不得把状态设置为 `lawyer_reviewed`。

## 禁止事项

- 不判断诉讼请求、合同条款或法律意见是否最终成立。
- 不自动删除具有实质内容的批注或修订；发现后阻断并要求人工处理。
- 不自动签名、盖章、发送、上传或提交。
- 不把机关官方原件改写后继续标称为官方原件。

