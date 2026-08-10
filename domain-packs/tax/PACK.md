# Taxation Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for taxpayers, transaction substance, tax types, filing and payment, audits, and remedy procedures
- Organization of calculation inputs and voucher chains for VAT, income tax, and other taxes

Excluded:

- Automatic filing and payment, automatic determination of tax evasion, automatic selection of tax incentives, or issuance of tax opinions

## Official Sources

- [中华人民共和国税收征收管理法](https://fgk.chinatax.gov.cn/zcfgk/c100009/c5195081/content.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国增值税法（自2026年1月1日起施行）](https://www.npc.gov.cn/npc/c2/c30834/202412/t20241225_442038.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国增值税法实施条例（国务院令第826号，自2026年1月1日起施行）](https://fgk.chinatax.gov.cn/zcfgk/c100010/c5246349/content.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Transactions and Tax-Type Identification

Must ask:

- What are the transaction parties, subject matter, consideration, place of performance, and invoice and fund flows?
- Is there official basis for the tax types, periods, rates, incentives, and local interpretations under discussion?

Fact fields:

- Transaction structure
- Place of performance
- Income and costs
- Invoices and funds

Suggested evidence:

- Contracts, orders, invoices, and bank flows
- Books, filing forms, and official policy versions

Calculation hooks (only accepts confirmed rules and variables):

- Hand over only manually confirmed tax base, rates, periods, and incentive inputs to cn-calc to generate a candidate calculation ledger

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate nodes for tax obligations, filing, and payment

Prohibited:

- Must not determine transaction substance and tax treatment from invoice descriptions alone

### Audits and Remedies

Must ask:

- What are the inspection notices, factual findings, evidence, calculation tables, and procedural nodes?
- Is the dispute a tax dispute, penalty, preservation, or enforcement measure, and what are the candidate remedy paths?

Fact fields:

- Administrative documents
- Found facts
- Tax calculations
- Service and remedies

Suggested evidence:

- Audit workpapers, interrogation transcripts, and electronic data
- Decision documents, service vouchers, and payment/guarantee materials

Calculation hooks (only accepts confirmed rules and variables):

- Itemized ledger of taxes, late fees, and fines

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate nodes for statements and defense, mandatory administrative reconsideration, and litigation

Prohibited:

- Must not automatically determine that the tax authority or the taxpayer violated the law

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not automatically send notices, filings, tax payments, reconsideration, or litigation applications, and must not submit to any external system
- Must not automatically deduct, offset, refund, select tax incentives, or perform other external operations
