---
name: cn-compliance-review
description: 将中国企业综合合规审查的范围、资料来源、现行法源、控制措施、测试结果、差距候选、风险分级和整改建议整理为可追溯底稿。用于常年法律顾问、专项合规检查、制度差距分析和整改跟踪；不用于仅凭风险提示自动认定违法、修改生产制度、处分员工、删除数据或向监管机关回复。
---

# 中国企业合规差距审查

## 流程

1. 明确审查主体、法域、截止日、专项范围和排除事项。
2. 由 `cn-research` 核验每项法源的官方全文、效力和适用时点。
3. 将控制描述、测试步骤、样本、结果和来源分别登记；“未测试”不得写成“不合规”。
4. 运行生成器：

```bash
.venv/bin/python skills/cn-compliance-review/scripts/build_review.py \
  skills/cn-compliance-review/examples/review.example.json \
  --output /path/to/new-review
```

5. 由律师和业务负责人确认风险等级、整改责任人、期限和是否实施。

输入契约见 [references/review-contract.md](references/review-contract.md)。

## 边界

- 每项测试和发现必须回到来源；法律差距还必须引用已核验法源。
- 输出只称“差距候选”或“风险候选”，不自动认定违法。
- 整改建议固定为 `not_implemented`，不修改制度、权限、数据或外部系统。
- 不对外发送、提交、签章或作监管承诺。
