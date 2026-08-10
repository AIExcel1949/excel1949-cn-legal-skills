---
name: cn-legal-letter
description: 根据中国律师已确认的当事人信息、事实来源、现行法源、金额旁路报告、要求事项和履行节点生成可追溯的律师函 JSON 与 Markdown 审查底稿。用于催告、权利通知、履约交涉和争议前沟通；不用于自动发送、邮寄、签章，不虚构法律后果、威胁收件人或把未核验事实写成确定陈述。
---

# 中国律师函底稿

## 流程

1. 逐项登记事实、要求事项、法源、计算报告和履行节点，不从用户目的反推缺失事实。
2. 金额只引用 `cn-calc` 的结果并保留律师确认状态；履行节点只引用已核验规则或用户确认的商业要求。
3. 运行生成器：

```bash
.venv/bin/python skills/cn-legal-letter/scripts/build_letter.py \
  skills/cn-legal-letter/examples/letter.example.json \
  --output /path/to/new-letter
```

4. 由执业律师核验措辞、法源、策略、送达方式、签署和用章；脚本不执行任何外部动作。

输入契约见 [references/letter-contract.md](references/letter-contract.md)。

## 阻断条件

- 事实或要求事项没有来源定位或用户确认记录；
- 引用法源未核验全文、效力状态不是现行有效；
- 引用金额尚未由律师确认；
- 要求自动发送、邮寄、签章，或输入承认存在虚构后果、侮辱、胁迫措辞；
- 输出目录已经存在。

输出固定为 `lawyer_review_required`，不生成印章、签名或可直接发送版本。
