---
name: cn-diligence
description: 将中国法律尽职调查的数据室文件、资料请求、事实发现、法律发现、例外、红旗、未提供材料和管理层陈述整理为可追溯律师复核底稿。用于并购、投融资、常年顾问、上市或其他非诉项目的资料室盘点和尽调发现汇总；不用于自动评估交易是否通过、正式签发报告或代替律师实质判断。
---

# 中国法律尽职调查底稿

## 执行流程

1. 固定数据室截止时点和项目法域，不把截止时点后的资料混入本轮底稿。
2. 为每份资料登记文件 ID、来源定位、SHA-256 和核验状态；不使用无来源的摘要。
3. 按 [schemas/diligence-input.schema.json](schemas/diligence-input.schema.json) 准备 JSON。字段口径见 [references/workpaper-rules.md](references/workpaper-rules.md)。
4. 验证并生成底稿：

   ```bash
   python scripts/build_diligence.py input.json --output output/diligence-workpaper
   ```

5. 由执业律师逐项复核来源、法源效力、例外与红旗分类，再决定是否进入正式尽调报告。

## 强制规则

- 每个事实发现、法律发现、例外和红旗至少引用一个已登记 `source_span`。
- 每个法律发现至少引用一条官方法源核验记录。效力不明、尚未生效、失效或待核验均阻断生产性使用。
- `not_provided` 仅表示截至数据室截止时点尚未提供，不得改写为相关事实或文件“不存在”。
- 管理层陈述单列，未经独立材料验证前不得升格为已确认事实。
- 固定输出 `artifact_state: lawyer_review_required` 和 `transaction_assessment: not_performed`。
- 输出目录必须不存在；脚本在同一文件系统内临时写入后原子更名，拒绝覆盖。

## 产出边界

- 输出 `diligence-workpaper.json` 和 `diligence-workpaper.md`，仅作律师复核底稿。
- 不生成正式签发报告，不给出“通过/不通过”结论，不自动签章、发送或修改数据室。
- 涉及现行法时先用 `cn-research` 核验官方法源，法律更新后用 `cn-law-update` 复核影响。

## 对外使用提示

1. AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。
2. 使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。
3. AI 不能替代律师对案件具体情况进行独立法律判断。
4. 本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。
5. AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。
