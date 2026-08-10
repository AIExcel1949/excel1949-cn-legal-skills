---
name: cn-dispute
description: 将中国大陆民商事诉讼、仲裁、调解、执行、刑事辩护和行政诉讼请求分流到正确的案件分析、证据、期限及文书工作流。用于争议解决路径和当事人角色已经由用户或律师确认、需要生成只读调用计划时；不用于自动选择程序、管辖、案由、仲裁机构或诉讼策略。
---

# 中国争议解决路由

## 流程

1. 核对争议类型、程序阶段、当事人角色和用户目标是否已确认。
2. 未确认时只输出缺口，不从案情描述猜测程序或诉讼地位。
3. 用确定性脚本生成工作流候选：

```bash
.venv/bin/python skills/cn-dispute/scripts/route.py \
  skills/cn-dispute/examples/route.example.json \
  --output /path/to/new-route.json
```

4. 由律师核对管辖、仲裁协议、期限、保全和冲突风险后再调用下游 Skill。

输入状态见 [references/routing-contract.md](references/routing-contract.md)。

## 边界

- 民事诉讼中只有明确角色为 `claimant` 或 `respondent` 才分别加入 `cn-complaint` 或 `cn-defense`。
- 紧急标记只升级人工审查，不计算期限、不提交申请。
- 不自动签名、盖章、发送、立案或对外承诺。
