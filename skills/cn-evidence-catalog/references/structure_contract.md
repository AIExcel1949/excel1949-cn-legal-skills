# Structure Contract — Evidence Catalog (证据目录)

User-authored reference contract (2026-08).

## Document Hierarchy

```
1. Case Title (案件名称) — centered, single line, line spacing 2.0
2. Main Heading (证 据 目 录) — centered, 黑体 18pt NOT bold, space between chars
3. Meta Block — 2 lines, left-aligned:
   Line 1: 提交人（原告/被告/第三人）：提交人名称   ("提交人（…）：" bold)
   Line 2: 提交时间：YYYY年M月D日                 ("提交时间：" bold)
4. Empty Separator Paragraph — 1 blank line, exact 10pt line spacing, no before/after
5. Evidence Items (evidence 一, evidence 二, ...):
   - Evidence heading: "证据一、" + brief description (ENTIRE line bold)
   - Proof-purpose paragraph: "证明目的：" (label bold) + content (regular)
```

No page breaks, no section breaks, no header, no tables, no images.

## Evidence Item Rules

- Numbering: Chinese numerals 一、二、三、四、五、六、七、八、九、十… followed by 顿号（、）.
- The prefix is part of the heading text (not an auto-numbered list style).
- Do not use Arabic numerals or parentheses for evidence numbering.

## Proof-Purpose Content Patterns

1. Simple single purpose: "证明目的：原、被告主体资格。"
2. Multi-point list: "证明目的：1、…；2、…；3、…" (Arabic numerals + 顿号, points separated by ；)
3. Descriptive paragraph: "证明目的：被告已向原告支付货款 318860 元，尚欠原告货款 305350 元。"

## Content Semantics

- Contract/law/document names in 《》 (Chinese book title marks).
- Supplementary info in full-width parentheses （）.
- Dates: YYYY年M月D日, no leading zeros on month/day.
- Reproduce content faithfully; never fabricate dates, amounts, weights, or contract terms.
