---
name: cn-verify
description: 对中国律师拟提交、发送、定稿或对外分享的法律文书执行结构化终检，核验事实、证据、法源、数字、日期、引文、内部一致性、敏感信息和待确认项，输出 blocker、warning、note 三级可审计 JSON 与 Markdown 报告。用于起诉状、答辩状、代理词、法律意见书、律师函、合同和其他法律工作成果的交付前审查；不用于直接重写原稿、自动签名盖章或替代执业律师定稿。
---

# 中国法律文书终检

## 执行边界

仅读取原稿和核验台账，不在原稿中直接改字，不自动将状态标记为 `lawyer_reviewed`。发现问题时只记录定位、核验理由和建议处理方向，不生成隐式替换文本。

## 准备输入

按 [references/input-contract.md](references/input-contract.md) 建立 JSON 核验包。事实、证据、法源、计算和期限记录与 `cn-legal-core` 对应 Schema 兼容。不得用模型推测值填补缺失字段。

真实文书设置 `mode=production`；脱敏教学数据必须显式设置 `mode=training_fixture`。对外公开稿设置 `privacy_mode` 为 `external_public`；法院、仲裁机构或客户交付稿设为 `case_submission`；内部草稿设为 `internal`。

## 运行终检

```bash
python scripts/verify_document.py \
  /path/to/verify-input.json \
  --artifact-file /path/to/original-document \
  --output-dir /path/to/new-review-output
```

从项目根目录使用 `.venv` 运行；首次使用先按根目录 `requirements.txt` 安装 `jsonschema` 等依赖。`--artifact-file` 为可选但生产终检建议必填，用于回读并核对 `artifact.input_sha256`；不提供时报告会明确记录原文件哈希尚未由本次脚本验证。

输出目录必须不存在。脚本以临时目录写入，成功后原子提交，不覆盖输入：

- `review-report.json`：机器可读审计记录；
- `review-report.md`：供律师阅读的问题清单。

脚本有 blocker 时退出码为 `1`，仅有 warning 或 note 时退出码为 `0`，输入或环境不可处理时退出码为 `2`。

如文书包含法条原文、裁判原文、规范性文件转述或同一命题的多个法源，先按 [references/citation-integrity.md](references/citation-integrity.md) 建立引用台账并执行：

```bash
python scripts/audit_citation_ledger.py \
  /path/to/citation-ledger.json \
  --output-dir /path/to/new-citation-audit
```

该审计把 `exact_quote`、`paraphrase` 和 `reference_only` 分开，核对文书字符锚点、法源定位、效力与核验状态；不会自行补写条文、案号或出处。

## 处理结果

按 [references/check-rules.md](references/check-rules.md) 理解规则和级别：

- `blocker`：未处理前不应提交、发送或公开；
- `warning`：存在实质或合规风险，由律师决定是否阻断；
- `note`：范围、限制或已执行检查的留痕。

拟引用的规范存在时间法、地域、主体、事项、程序范围或法源冲突问题时，读取 [references/norm-applicability.md](references/norm-applicability.md)，在终检前建立独立适用性台账。

将报告与原稿哈希一并归档。如原稿发生变化，必须生成新的核验包并重新终检，不得沿用旧报告。

## 质量门禁

1. 不伪造事实、证据、法条、案例、日期、金额或律师确认。
2. 法源未核验效力或依据已废止时，不得将报告标记为可交付。
3. 事实冲突、必要证据缺口、计算不一致、引文无法回查或必填占位符残留一律输出 blocker。
4. 报告中的敏感信息证据片段必须脱敏，不复制完整身份证号、手机号、银行卡号或邮箱。
5. 所有 blocker 清零后仍只能输出 `machine_checked`，最终签发由执业律师逐项确认。
