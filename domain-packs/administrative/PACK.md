# Administrative & Regulatory Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for administrative acts, administrative reconsideration, administrative litigation, administrative compensation, and enforcement linkage
- Checklists of subject, authority, procedure, evidence, service, and remedy nodes

Excluded:

- Automatic determination of justiciability, mandatory administrative reconsideration, jurisdiction, limitation periods, unlawfulness of administrative acts, or compensation liability

## Official Sources

- [中华人民共和国行政复议法（2023年修订，自2024年1月1日起施行）](https://www.npc.gov.cn/npc/c2/c30834/202309/t20230901_431401.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国行政诉讼法](https://www.npc.gov.cn/zgrdw/npc/xinwen/2017-06/29/content_2024894.htm)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Administrative Acts and Remedy Entry

Must ask:

- Which authority issued the act, what is its jurisdictional basis, target, content, and actual impact?
- What are the act's form, service, performance, mandatory administrative reconsideration status, and prior remedy history?

Fact fields:

- Administrative subject
- Act content
- Jurisdictional basis
- Service and impact

Suggested evidence:

- Decisions, notices, inspection, and service materials
- Applications, complaints, reconsideration, and reply records

Deadline hooks (node identification only; no statutory deadlines computed):

- Application, service, reconsideration, and filing node candidates

Prohibited:

- Must not automatically determine that an act is justiciable, subject to mandatory reconsideration, or time-barred

### Procedure, Evidence, and Claims

Must ask:

- Which investigation, hearing, notification, and statement-of-reasons procedures did the administrative authority perform?
- What are the plaintiff's standing, claim objectives, facts and evidence, and needs for incidental review of regulatory documents (规范性文件附带审查)?

Fact fields:

- Investigation procedure
- Notification and hearing
- Evidence basis
- Remedy claims

Suggested evidence:

- Enforcement case files, transcripts, hearing, and approval records
- Regulatory documents, application materials, and damage vouchers

Calculation hooks (only accepts confirmed rules and variables):

- Ledger of loss and compensation items

Deadline hooks (node identification only; no statutory deadlines computed):

- Evidence production, hearing, and performance node candidates

Prohibited:

- Must not derive rescission, unlawfulness confirmation, or compensation conclusions automatically from procedural-defect candidates

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not automatically send notices, applications, reconsideration, litigation, or performance materials, and must not submit to any external system
- Must not automatically apply for or execute suspension, rescission, coercion, compensation, or other external operations
