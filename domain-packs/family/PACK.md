# Family & Inheritance Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for marriage validity, divorce, child custody, and marital property and debt
- Checklists of identity, property, care, and safety risks in family cases
- Evidence hints for property leads and custody arrangements

Excluded:

- Automatic legal conclusions on succession, adoption, foreign-related family matters, and emergency handling of domestic violence

## Official Sources

- [中华人民共和国民法典](https://www.moj.gov.cn/pub/sfbgw/zwgkztzl/2025nianzhuanti/2025mfdxcy/2025mfdxcy_mfdql/202505/t20250507_518708.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释（二）](https://www.court.gov.cn/zixun/xiangqing/458581.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Marriage Relationship and Divorce

Must ask:

- What are the marriage registration, cohabitation, separation, and prior litigation history?
- Are the parties' statements on the state of affection, divorce intent, and fault facts consistent?
- Are there urgent risks to personal safety, minors, or property transfer?

Fact fields:

- Marriage registration
- Cohabitation and separation
- Prior litigation
- Safety risks

Suggested evidence:

- Marriage registration and identity materials
- Separation, communication, and residence materials
- Police reports, admonition letters, medical treatment, or protection order materials

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate nodes for prior judgments becoming final and refiling

Prohibited:

- Must not downplay signals of domestic violence, physical danger, or minor-child safety

### Child Custody and Visitation

Must ask:

- What are the children's age, health, schooling, and actual care arrangements?
- What are each party's care time, living conditions, income, and support networks?
- How will the children's wishes be learned lawfully, age-appropriately, and without inducement?

Fact fields:

- Children's basic information
- Actual care
- Education and medical care
- Both parties' custody plans
- Visitation arrangements

Suggested evidence:

- Birth and enrollment materials
- Daily care, medical, and expense vouchers
- Residence and support-network materials

Calculation hooks (only accepts confirmed rules and variables):

- Ledger of child-support expense items and ability to pay

Deadline hooks (node identification only; no statutory deadlines computed):

- Temporary arrangements or urgent protection nodes

Prohibited:

- Must not automatically decide custody arrangements based on a single income level

### Marital Property and Debt

Must ask:

- What are the acquisition time, funding source, registration, control, and current value of each asset?
- Are there materials on gifts, parental contributions, transformation of pre-marital property, and marital agreements?
- What are the formation, purpose, common intent, and benefit of each debt?

Fact fields:

- Property list
- Acquisition and funding
- Registration and control
- Debt list
- Property transfer leads

Suggested evidence:

- Real estate, vehicle, equity, and account materials
- Contribution flows, gift or loan statements
- Debt contracts, purpose, and joint-confirmation materials

Calculation hooks (only accepts confirmed rules and variables):

- Property valuation and division scenarios
- Ledger of debt balances and repayments

Deadline hooks (node identification only; no statutory deadlines computed):

- Urgent nodes for property preservation or evidence collection

Prohibited:

- Must not determine ultimate ownership or debt nature from registered names alone

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not replace risk handling with automated efficiency in matters involving minors and personal safety
