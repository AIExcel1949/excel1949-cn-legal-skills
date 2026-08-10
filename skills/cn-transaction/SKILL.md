---
name: cn-transaction
description: 将中国律师合同起草审查、法律尽调、公司治理、并购、法律意见、律师函和交易谈判任务分流到对应非诉工作流。用于交易阶段、任务类型和代表立场已经由用户或律师确认、需要建立材料—审查—交付调用顺序时；不用于自动批准交易、替客户接受条款或给出最终法律意见。
---

# 中国交易非诉路由

## 流程

1. 确认任务类型、交易阶段、代表立场、法域和预期交付物。
2. 未由用户确认时只输出阻断项，不从文件名或对方来函推断授权。
3. 运行只读路由器：

```bash
.venv/bin/python skills/cn-transaction/scripts/route.py \
  skills/cn-transaction/examples/route.example.json \
  --output /path/to/new-route.json
```

4. 先做收案和法源核验，再执行专业工作流，最终交给 `cn-verify`。

状态说明见 [references/routing-contract.md](references/routing-contract.md)。

## 边界

- 不替客户确认商业底线、特别授权、陈述保证、交割条件或签署版本。
- 不自动发送律师函、合同或意见书，不签章、不提交。
- 交易类型与代表立场冲突时必须人工拆分任务。
