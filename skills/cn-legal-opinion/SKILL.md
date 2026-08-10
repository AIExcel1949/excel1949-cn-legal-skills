---
name: cn-legal-opinion
description: 将中国法律问题、法域与时点、已确认事实、假设、限制、已核验法源、正反分析命题和条件性结论整理为可追溯的 JSON 与 Markdown 律师复核底稿。用于法律意见分析、顾问答复、交易结论论证或正式意见书签发前的内部质量控制；不用于冒充正式签发意见书、自动签章或发送。
---

# 中国法律意见分析底稿

## 执行流程

1. 明确问题、中国法域范围和意见时点，不用后续发生事项倒推。
2. 将已确认、冲突和未核验事实分开；每项事实保留来源定位和来源哈希。
3. 将假设与事实分开，标明关键假设是否已确认；单列调查范围和用途限制。
4. 通过 `cn-research` 核验官方法源全文、效力和意见时点适用性，再按 [schemas/opinion-input.schema.json](schemas/opinion-input.schema.json) 准备 JSON。详细口径见 [references/opinion-rules.md](references/opinion-rules.md)。
5. 生成确定性底稿：

   ```bash
   python scripts/build_opinion.py input.json --output output/opinion-workpaper
   ```

6. 由执业律师对事实、法源、正反命题、条件和限制逐项复核；如需正式意见书，在本 Skill 之外另行起草和签发。

## 强制门禁

- 每个分析命题和结论草案必须同时引用至少一项事实与一条已登记法源。
- 存在冲突事实、结论依赖未确认事实、失效/效力不明/待核验法源，或关键假设未确认时，结论状态必须为 `blocked`。
- 即使无额外阻断项，结论也只能为 `provisional_for_lawyer_review`，不得标记为正式签发。
- 固定输出 `artifact_state: lawyer_review_required` 和 `formal_opinion_issued: false`。
- 输出目录必须不存在；脚本使用同文件系统临时目录和原子更名，拒绝覆盖。

## 输出边界

- 输出 `opinion-workpaper.json` 和 `opinion-workpaper.md`，标题和正文均明示为“律师复核底稿”。
- 不生成签名页、律所盖章页或发送指令，不以任何文件名冒充正式法律意见书。
- 法律变更可能影响结论时，先用 `cn-law-update` 复核时点与过渡规则。

## 对外使用提示

1. AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。
2. 使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。
3. AI 不能替代律师对案件具体情况进行独立法律判断。
4. 本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。
5. AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。
