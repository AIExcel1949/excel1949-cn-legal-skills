# 运行时输出契约

## 路径

- Skill 安装目录及其 `references/`、`assets/`、`examples/`、`schemas/`、`scripts/` 均为只读资源区，不得保存案件材料、草稿、日志、预览或生成结果。
- 运行前分别确定 `SKILL_ROOT` 与 `PROJECT_ROOT`。脚本和预设模板从 `SKILL_ROOT` 读取，案件产物写入 `PROJECT_ROOT`。
- 用户未指定目录时，默认使用 `<PROJECT_ROOT>/output/cases/<matter-id>/cn-procedure`。`matter-id` 缺失时先建立稳定任务编号，不得用 Skill 目录代替案件目录。
- 传给 `--output` 的路径必须是绝对路径、必须尚不存在，并且不得位于任何已安装 Skill 的共同目录内。
- 不得先 `cd` 到 Skill 目录再使用相对输出路径。

## 产物

用户要求生成、制作、导出或交付程序文书时，必须直接调用 `scripts/fill_templates.py`，输出：

1. 按用户明确选择的模板或文书包生成的一份或多份 `.docx`；
2. 一份 `generation-manifest.json`，记录模板标识、预设模板相对路径、模板哈希、生成文件哈希和本次加载的参考文件哈希。

除非用户明确要求，不生成同名 Markdown、纯文本或 PDF 副本。不得把 Markdown 机械转换为 DOCX 后冒充预设模板产物。

## 模板来源

- 所函、授权委托书、委托代理合同、法律顾问合同和审批表只使用 `schemas/template-manifest.json` 已登记的预设 DOCX。
- 加强版申请书和身份证明只在用户明确要求且专门事实已经具备时使用。
- 《最高人民法院民事诉讼文书样式·制作规范与法律依据（律师与当事人卷）》只提供文种、栏目和版式结构参考；其中法条、期限、机关信息和程序条件不得直接进入交付件。
- 模板版式来源和法律核验来源必须分别记录；具体规则见 `source-governance.md`。
- `scripts/build_templates.py` 是维护者重建预设模板的内部工具，不是案件文书生成器。办理具体案件时禁止运行。
- 用户要求扩张文书集合时，可以调用其他对应 Skill；每份产物必须记录来源 Skill 和生成器，不得由 `cn-procedure` 越权临时起草未登记文书。

## 交付门禁

- `generation-manifest.json` 中登记的 DOCX 集合必须与目录中的 DOCX 完全一致。
- 每份 DOCX 必须通过 `scripts/audit_templates.py`，并逐页渲染检查。
- 作者与最后修改者必须为 `AIOffice职场通关-excel1949`，页眉页脚必须保留 AIOffice 真实 Logo 和页码。
- 任一模板来源、文件哈希、必填字段或版式检查不通过，不得交付。
