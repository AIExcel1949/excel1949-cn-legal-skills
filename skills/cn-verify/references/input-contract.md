# 终检输入契约

## 数据来源

核验包是对原稿与案件台账的只读快照。`artifact.input_sha256` 记录原文件哈希，`artifact.text_sha256` 记录待检文本 UTF-8 字节哈希。两者用途不同，不得互相填充。

生产终检应通过 CLI 的 `--artifact-file` 传入只读原文件，让脚本重新计算并核对 `artifact.input_sha256`。未提供原文件时，脚本只能校验文本哈希，并在报告中留下未回读原文件的范围说明。

`review_context.mode` 必须明确区分 `production` 与 `training_fixture`。教学模式只是标记数据用途，不降低任何终检规则。

`facts[].record`、`evidence[].record`、`authorities[].record`、`calculations[].record` 和 `deadlines[].record` 分别对应 `cn-legal-core` 的事实、证据、法源、计算和期限 Schema。未知、冲突、争议和人工确认状态必须保留。

## 文本映射

- `display_text`：台账值在原稿中应出现的字面形式。
- `required_in_document`：缺失该文本映射是否阻断交付。
- `evidence_required`：该事实是否必须在证据台账中建立关联。
- `relied_upon`：文书是否将该法源或期限作为当前结论依据。

脚本只能校验已提供的映射，不会从自由文本中推断当事人真实意思、证据真实性或法律结论。

## 隐私模式

| 值 | 用途 | 敏感信息处理 |
|---|---|---|
| `internal` | 律所内部工作稿 | 输出 warning，要求核验授权和保存范围 |
| `case_submission` | 向法院、仲裁机构、客户或相对方提交 | 输出 warning，要求核验必要性与收件人 |
| `external_public` | 公开发布、教学、宣传或不特定分享 | 检出身份证号、手机号、银行卡号或邮箱即 blocker |

## 人工确认

`human_confirmations` 必须使用显式状态：

- `pending`：尚未确认；
- `confirmed`：已由具名人员在指定时间确认；
- `rejected`：明确否定，必须重新评估原稿。

必要确认项为 `pending` 或 `rejected` 时输出 blocker。脚本不会自动改为 `confirmed`。
