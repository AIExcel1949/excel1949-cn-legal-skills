# Style Contract — Evidence Catalog (证据目录)

User-authored reference contract (2026-08), derived from a concrete court DOCX artifact.

## Page Layout

| Property | Value |
|----------|-------|
| Paper size | A4 (21 cm × 29.7 cm), portrait |
| Top margin | 2.5 cm |
| Bottom margin | 2.0 cm |
| Left margin | 2.5 cm |
| Right margin | 2.0 cm |

## Typography

| Element | Font | Size | Weight | Line Spacing |
|---------|------|------|--------|--------------|
| Case title | 仿宋 (FangSong) | 14pt | Regular | 2.0 (multiple) |
| Main heading "证 据 目 录" | 黑体 (HeiTi) | 18pt | **Not bold** | 1.5 (multiple) |
| Meta labels (提交人/提交时间) | 仿宋 | 14pt | **Bold** | Exact 26pt |
| Meta values | 仿宋 | 14pt | Regular | Exact 26pt |
| Evidence heading (证据一、…) | 仿宋 | 14pt | **Bold (entire line)** | Exact 26pt |
| Proof-purpose body | 仿宋 | 14pt | Regular ("证明目的：" label bold) | Exact 26pt |
| Blank separator | — | — | — | Exact 10pt (200 twips) |

## Paragraph Spacing

- Body paragraphs: before = 156 twips (7.8pt), after = 156 twips.
- Blank separator: before/after = 0.
- Exact line spacing expressed as 520 twentieths (26pt) for body paragraphs; 200 twentieths (10pt) for the separator.

## Colors

- All text black (#000000) on white. No accent colors, no borders, no shading.

## Footer

- Page number "X / Y" (PAGE/NUMPAGES fields) centered, bold, 12pt in the reference.
- In this cluster, the footer is rendered by the compact brand footer (brand name + "第 N 页" page field) to keep brand consistency; the page number requirement is preserved.

## Font Substitution

- FangSong primary; fallback 仿宋_GB2312; final fallback any CJK serif (宋体, 思源宋体).
- HeiTi primary; fallback 华文黑体, 思源黑体.
- Never fall back to Latin-only fonts for Chinese text.

## No Header, No Tables, No Charts, No Images

- No header; footer contains only the brand page number.
- No tables, no embedded images or charts; pure text catalog.
