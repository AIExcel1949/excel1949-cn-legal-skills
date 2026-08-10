---
name: cn-evidence-catalog
description: 生成中国法院标准的《证据目录》DOCX（案件名称、证 据 目 录标题、提交人/提交时间、证据一/二…编号、证明目的），排版对齐用户自制法院参考契约（仿宋正文、黑体 18pt 不加粗标题、精确行距、页码）。用于证据目录、证据清单、提交证据列表、证据材料整理；不判断证据三性或证明力，不自动签章提交。
---

# Evidence Catalog (证据目录) Generator

Produce a court-standard evidence catalog DOCX per the user-authored evidence-catalog-docx contract (2026-08).

## Reference Contract

- Full style spec: `references/style_contract.md`; full structure spec: `references/structure_contract.md`.
- Typography (MANDATORY): body in **仿宋 (FangSong) 14pt**; main heading "证 据 目 录" in **黑体 (HeiTi) 18pt, NOT bold**, centered, with a space between each character; exact **26pt line spacing**; paragraph before/after **156 twips**; margins top 2.5 / bottom 2.0 / left 2.5 / right 2.0 cm.
- Structure: case title (centered) → "证 据 目 录" → 提交人（角色）：提交人 (label bold) → 提交时间：YYYY年M月D日 (label bold) → blank separator (exact 10pt) → evidence items.
- Evidence items: "证据一、" + title (**entire line bold**, Chinese numerals 一、二、… + 顿号); next line "证明目的：" (label bold) + regular content; multi-point purposes use 1、2、3、 separated by ；.
- No header, no tables, no images in body. Footer: cluster brand page number via `cn-legal-core` compact branding; author MUST be `AIOffice职场通关-excel1949`.

## Execution

Prepare input per `schemas/evidence-catalog-input.schema.json`, then:

```bash
python scripts/render_evidence_catalog.py --input catalog.json --output <new-dir>/证据目录.docx
```

## Content Accuracy (MANDATORY)

- Reproduce user-provided content faithfully: exact dates, amounts, weights, contract terms, document titles.
- NEVER fabricate, modify or anonymize evidence details unless explicitly instructed.
- Use Chinese book title marks 《》 for contract/law names; full-width parentheses （） for supplementary info; date format YYYY年M月D日 (no leading zeros).

## Blocking Conditions

- Evidence item without source or `user_confirmed` record;
- User asks for automatic signature, seal, e-filing or submission → refuse.
- Output DOCX only; JSON is internal data.
