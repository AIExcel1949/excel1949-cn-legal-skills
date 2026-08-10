# Tort & Damages Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Organization of fact elements for general torts, joint torts, and personal injury
- Identification of damage items, causation, fault, and liable-subject candidates
- Checklist of vouchers for medical, lost income, care, and other losses

Excluded:

- Final liability determinations in special areas such as medical damage, environmental torts, product liability, and online torts

## Official Sources

- [中华人民共和国民法典](https://www.moj.gov.cn/pub/sfbgw/zwgkztzl/2025nianzhuanti/2025mfdxcy/2025mfdxcy_mfdql/202505/t20250507_518708.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于审理人身损害赔偿案件适用法律若干问题的解释](https://gongbao.court.gov.cn/Details/4d16a63992ba473f7f5885565cc13a.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Conduct, Fault, and Subjects

Must ask:

- What are the specific conduct, actor, person in control, and source of the duty of care?
- Does the injured party claim joint torts, vicarious liability, or security obligations (安全保障义务)?
- Do the parties raise contributory fault, third-party causes, or grounds for exemption?

Fact fields:

- Course of conduct
- Actor and control relationship
- Source of the duty of care
- Fault statements of each party

Suggested evidence:

- Original site videos, photos, and electronic data
- Subject relationships, employment, or management materials
- Police reports, investigation, or accident-determination materials

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate dates of damage occurrence or discovery

Prohibited:

- Must not infer that the actor necessarily had fault from the damage result alone

### Causation and Damage

Must ask:

- What are the timeline and intervening events between the conduct and the damage?
- How do pre-existing conditions, later treatment, third-party intervention, and damage aggravation affect the dispute?
- What materials exist on each loss's occurrence, payer, and necessity?

Fact fields:

- Injury and treatment timeline
- Pre-existing conditions
- Damage items
- Paying parties
- Later effects

Suggested evidence:

- Medical records, examinations, diagnoses, and expense receipts
- Income, lost-work, care, and transportation materials
- Appraisal opinions and sample sources

Calculation hooks (only accepts confirmed rules and variables):

- Item-by-item calculation of damage items
- Candidate deductions for amounts already paid and insurance payments

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate nodes for disability or damage determination

Prohibited:

- Must not use total medical receipts in place of verification of necessity, relevance, and actual burden

### Liability Allocation and Remedies

Must ask:

- Is the list of potentially liable parties complete and their identities verifiable?
- Which verified rules and facts support the liability forms and ratios?
- Do insurance, work injury, contractual liability, or other claims compete (请求权竞合)?

Fact fields:

- Liable-party list
- Liability-form claims
- Insurance and payments
- Competing claims

Suggested evidence:

- Insurance contracts and claim records
- Labor or contract-for-work relationship materials
- Evidence of each joint tortfeasor's conduct

Calculation hooks (only accepts confirmed rules and variables):

- Liability ratios are only manually confirmed inputs
- Ledger of payment deductions

Deadline hooks (node identification only; no statutory deadlines computed):

- Limitation-period candidates for each claim

Prohibited:

- Must not let the model arbitrarily set liability ratios

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
