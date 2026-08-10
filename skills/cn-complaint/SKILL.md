---
name: cn-complaint
description: 生成中国民事起诉状（民事起诉状）的正式 DOCX，排版对齐法院立案标准（仿宋、固定行距、中文数字诉请、事实与理由连续书写）。用于起诉状起草、诉状排版、起诉材料准备；不自动选择案由或诉讼策略，不生成签名印章。
---

# Civil Complaint Generator (民事起诉状)

Generate a formal civil complaint DOCX with court-filing typography (user-authored reference contract, 2026-08).

## Mandatory Reading

1. Read `references/contract.md` first, then prepare input per `schemas/complaint-input.schema.json`.
2. Only use court, parties, claims, facts and grounds bound to `source_spans` or `user_confirmed: true`. Never infer from context.

## Execution

Step 1 — build the structured draft:

```bash
python scripts/build_complaint.py --input <input.json> --output-dir <new-directory>
```

Step 2 — verify `complaint.json`: `claim_conservation_audit`, `blockers`, `gaps`. Any missing item, unresolved conflict, unverified legal source or pending confirmation MUST remain a blocker.

Step 3 — render the delivery DOCX (default delivery format; never hand the user raw JSON):

```bash
python scripts/render_docx.py --input <new-directory>/complaint.json \
  --output <new-directory>/民事起诉状.docx
```

## Typography Contract (MANDATORY)

- Entire document in **仿宋 (FangSong)**; title "民事起诉状" **18pt, NOT bold**, centered.
- Labels (原告/被告/案由/诉讼请求/事实与理由) **bold 14pt inline**; body **14pt regular**.
- Fixed line spacing **25pt (EXACT)**; first-line indent **28pt** (2 chars); wrapped lines flush left.
- Margins: left 25mm / right 20mm / top 30mm / bottom 20mm. A4.
- Claims numbered with Chinese numerals (**一、二、三、**), not Arabic.
- **事实与理由**: continuous narrative paragraphs, NO sub-headings, NO internal ids (fact_id/ground_id must never appear).
- Closing: 此致 (indent) → court name (flush left) → exactly TWO spacer paragraphs → 具状人 (indent ~15 chars) → date in Chinese uppercase numerals (二〇二二年三月二十一日).
- Header/footer: compact brand (small header logo + brand name + page number) via `cn-legal-core` `docx_brand(compact=True)`. Author/last-modified MUST be `AIOffice职场通关-excel1949`.

## Blocking Conditions

- Claims missing, reordered, merged or rewritten (claim conservation MUST hold);
- Unresolved conflicts, evidence gaps, unverified sources;
- User asks for signature, seal, e-filing, or automatic submission → refuse.

## Hard Rules

- Never compute, adjust or infer amounts, interest, dates or fee items.
- Never fabricate facts, party identities, case numbers or court names.
- Never generate signatures, seals or stamps; date left blank unless provided.
- Deliver DOCX only; JSON is internal data. Mark output for lawyer review (`artifact_state` stays `lawyer_review_required`).
