---
name: cn-compliance
description: 将中国企业劳动用工、数据与个人信息、公司治理、广告消费者、竞争及综合合规审查事项分流到对应工作流和领域业务包。用于合规主题、审查对象、法域和交付目标已由用户或律师确认、需要建立现状—规则—差距—整改链路时；不用于自动认定违法、批准整改或替企业作监管回复。
---

# 中国企业合规路由

## 流程

1. 核对合规主题、法域、审查对象、数据截止日和交付范围。
2. 未确认主题时只列缺口，不从材料中的关键词自动认定违法风险。
3. 运行路由器：

```bash
.venv/bin/python skills/cn-compliance/scripts/route.py \
  skills/cn-compliance/examples/route.example.json \
  --output /path/to/new-route.json
```

4. 由 `cn-research` 核验现行规则和地方口径，再执行专项 Skill；最终用 `cn-verify` 只读终检。

数据契约见 [references/routing-contract.md](references/routing-contract.md)。

## 边界

- 不自动修改制度、删除数据、处分员工、向监管机关回复或对外发布。
- 不把规则清单直接写成“已违法”结论。
- 监管时限和整改优先级需要律师及业务负责人确认。
