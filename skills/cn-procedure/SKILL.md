---
name: cn-procedure
description: 为中国律师生成、批量填充和核验程序文书与律所内部流程文书（所函、授权委托书、委托代理合同、法律顾问合同、收案用章审批、撤诉与保全等申请书），支持民事、刑事、行政、执行程序，版本化 JSON 案件数据 + DOCX 模板 + 未填字段拦截 + 跨文书一致性检查。正文排版对齐法院标准（仿宋、固定 25pt 行距、纯黑字体）。
---

# Chinese Procedural Documents (程序文书)

Generate, batch-fill and verify procedural documents and firm-internal workflow documents. Typography follows court-filing standards: FangSong body, fixed 25pt line spacing, **pure black text only** (no colored fonts in court-bound documents).

## Mandatory Reading (BEFORE any generation)

1. `references/output-contract.md`
2. `references/template-catalog.md`
3. `references/data-contract.md`
4. `references/legal-basis.md`
5. `references/judicial-practice-guide.md`
6. `references/source-governance.md`
7. `schemas/template-manifest.json`

Record this skill's absolute path as `SKILL_ROOT`, the user's project root as `PROJECT_ROOT`. Read scripts/schemas/templates ONLY from `SKILL_ROOT`; write ALL case input, drafts and artifacts ONLY under `PROJECT_ROOT`. Never write runtime artifacts into the skill install directory.

When the user requests DOCX, you MUST run `scripts/fill_templates.py` against registered preset DOCX templates and deliver actual `.docx` plus `generation-manifest.json`. Never return Markdown or "you can convert it yourself" instructions; never pass off Markdown-to-DOCX conversion as a preset-template product.

## Core Principles

Templates are structural drafts to be verified — NOT current legal conclusions. The 2016 最高院《民事诉讼文书样式》 is for document-type/stage/column identification only, never a source of current statutes, deadlines or procedural conditions (see `references/source-governance.md`). Confirm procedure, document purpose and acting party BEFORE selecting templates; never default to a fixed "five-piece set".

Workflow: **enter once → fill deterministically → verify each document**:

1. Extract facts from user materials; never invent names, ID/case numbers, bar numbers, authorization scope, fees or signing dates.
2. Write facts into versioned JSON per `schemas/case-data.schema.json` (fields per `references/data-contract.md`).
3. Select a bundle or single template per `schemas/template-manifest.json` (`references/template-catalog.md`).
4. Validate BEFORE filling; STOP delivery on any missing required field, field conflict or leftover template placeholder.
5. Human-verify legal applicability, fee rules, authorization scope, jurisdiction and local court requirements (`references/legal-basis.md`, `references/judicial-practice-guide.md`).
6. Render and page-inspect EVERY DOCX to deliver; "script ran OK" never substitutes for layout acceptance.

## Selecting a Bundle

- `civil-onboarding`: civil firm letter, lawyer power of attorney, general engagement contract, intake approval.
- `civil-risk-onboarding`: civil firm letter, lawyer power of attorney, **risk-fee** engagement, intake approval. Verify risk-fee prohibitions and fee caps first.
- `criminal-onboarding`: criminal firm letter, criminal power of attorney, criminal engagement, intake approval.
- `administrative-onboarding`: administrative power of attorney, administrative engagement, intake approval.
- `internal-approval`: intake/seal/closing approvals; the 3-in-1 form is a summary only, never a substitute for individual records.
- `legal-advisor`: annual legal-advisor contract (not a default litigation bundle).

Near-relative agency, execution agency or enhanced applications → use single templates, not the bundles above.

## Preparing Case Data

Copy `examples/case-data.example.json` (general lawyer agency), `examples/organization-employee-case-data.example.json` (staff agency) or `examples/property-preservation-case-data.example.json` (preservation). Keep only fact-supported values. Machine fields are lowercase snake_case (`lawyer_name`); never mix `lawyerName`/`律师姓名` aliases in one task.

Placeholder stability comes from SIX layers, not from `{{lawyer_name}}` itself:
1. fixed field names + `schema_version`;
2. explicit required/optional/never-infer fields;
3. per-template required-field declarations;
4. type/enum validation for amounts, dates, authorization options;
5. ONE shared JSON across documents — the model must not rewrite per document;
6. post-output placeholder interception with manifest + hashes.

Amounts: `fee_amount`/`annual_fee` etc. are Arabic numerals; matching `*_cn` fields are Chinese uppercase. Mismatch → STOP.

Risk-fee bundle: `risk_agency_confirmed` MUST be `yes` with lawyer-confirmed `risk_fee_terms`. Confirmation only records the manual gate; it does not make the template or ratio legal.

## Execution

Never set the skill directory as working directory. Use absolute paths for scripts, inputs and outputs.

Pre-check:

```bash
python <SKILL_ROOT>/scripts/fill_templates.py \
  --data <PROJECT_ROOT>/matter-data/case-data.json \
  --bundle civil-onboarding \
  --output <PROJECT_ROOT>/output/cases/<matter-id>/cn-procedure \
  --check
```

Generate:

```bash
python <SKILL_ROOT>/scripts/fill_templates.py \
  --data <PROJECT_ROOT>/matter-data/case-data.json \
  --bundle civil-onboarding \
  --output <PROJECT_ROOT>/output/cases/<matter-id>/cn-procedure
```

Single template:

```bash
python <SKILL_ROOT>/scripts/fill_templates.py \
  --data <PROJECT_ROOT>/matter-data/case-data.json \
  --template civil-power-attorney \
  --output <PROJECT_ROOT>/output/cases/<matter-id>/cn-procedure
```

Output directory: absolute, MUST NOT pre-exist, MUST be outside the skill directory. Batch generation stages in a temp dir then commits atomically. DOCX core properties: author and last-modified BOTH `AIOffice职场通关-excel1949`; never write real personal names into document properties.

## Quality Gates (before delivery)

1. Run `python <SKILL_ROOT>/scripts/audit_templates.py --path <PROJECT_ROOT>/output/cases/<matter-id>/cn-procedure`.
2. No `{{...}}`, example values, real-source law-firm names, unauthorized seal images or blank required fields.
3. Parties, cause, court, case number, lawyer, amounts and dates consistent across ALL documents.
4. Special authorization itemized; "全权代理" alone never creates special-authority effect.
5. Criminal stage, agency identity and principal identity must not be conflated (suspect ≠ defendant ≠ relative).
6. Risk-fee prohibitions, tiered caps, local rules and written risk notice verified.
7. Convert EVERY DOCX to per-page PNG; inspect text, tables, header/footer, pagination and fonts.
8. Retained lawyer confirms and signs each document; the skill never signs, seals, sends or files.

## Prohibitions

- No fabricated evidence, facts, bar numbers, case numbers, service info or court names.
- No auto-selection of special authorization, criminal stage, fee method, risk-fee ratio or conflict conclusions.
- No risk-fee templates for matters where risk fees are prohibited.
- No auto-insertion of seals, signatures, license scans or former-firm logos.
- No statute-number-as-verification; on template/current-rule conflict, STOP and explain.
- No inheriting statutes, deadlines, organ names, procedural conditions or examples from historical style PDFs.
- Never present working templates as court-issued "official templates"; never generate court-judgment impersonations.
- Never treat sample rates, termination or jurisdiction clauses as binding final contracts.
- NEVER run `scripts/build_templates.py` for a live case — maintainers only.
- No runtime I/O into the skill directory; no relative output paths from it.
- No generic Markdown-to-Word, blank python-docx or ad-hoc layouts in place of registered preset templates.
- Court-bound documents (起诉状/申请书/证据目录/授权委托书等) MUST be pure black text.

## Usage Notice

1. AI-generated legal documents are for learning/reference only, not for filing with courts or serving counterparties.
2. A licensed lawyer must verify facts and legal application before any use.
3. AI cannot replace a lawyer's independent legal judgment on the specific case.
4. Final documents must be reviewed and confirmed case-by-case by a licensed lawyer.
