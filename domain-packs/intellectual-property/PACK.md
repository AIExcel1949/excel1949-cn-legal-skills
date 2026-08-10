# Intellectual Property Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Organization of rights basis, use conduct, and damage materials for copyright, trademarks, patents, and trade secrets
- Verification entry points for licenses and assignments, platform evidence, and technical facts

Excluded:

- Automatic determination of patent validity, technical comparison, confusion, substantial similarity, or infringement

## Official Sources

- [中华人民共和国著作权法](https://www.npc.gov.cn/c2/c30834/202011/t20201119_308796.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国商标法（2019年修正）](https://flk.npc.gov.cn/detail?id=ff8080816f135f46016f217645451b35)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国专利法（2020年修正）](https://www.npc.gov.cn/npc/c2/c30834/202011/t20201119_308800.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国反不正当竞争法（2025年修订）](https://www.npc.gov.cn/npc/c2/c30834/202506/t20250627_446247.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Rights Basis and Chain of Title

Must ask:

- What are the subject matter of rights, authors/inventors, applications and registrations, and first public disclosure?
- Is the chain of employment-created works, commissioned creation, licenses and assignments, and renewal/fee payments complete?

Fact fields:

- Subject matter of rights
- Time of creation
- Title holders
- License and assignment chain

Suggested evidence:

- Drafts, source files, registration certificates, and official archives
- Employment/commission contracts, license and assignment, and payment materials

Deadline hooks (node identification only; no statutory deadlines computed):

- Fact-node candidates for applications, renewals, protection periods, and oppositions; no deadlines computed

Prohibited:

- Must not determine the full scope of rights and actual title from registration certificates alone

### Use Conduct and Comparison

Must ask:

- How are the subject, time, place, channel, and original carrier of the alleged conduct fixed?
- What are the comparison objects, possibility of access, technical features, or mark-use scenarios?

Fact fields:

- Conduct subjects
- Time and place of use
- Comparison objects
- Transaction scale

Suggested evidence:

- Notarized webpages, source code, or original physical items
- Purchase chains, platform records, and technical descriptions

Calculation hooks (only accepts confirmed rules and variables):

- Candidate ledger of sales, license fees, and losses

Deadline hooks (node identification only; no statutory deadlines computed):

- Evidence collection, notice, and limitation period nodes

Prohibited:

- Must not let a language model replace judicial appraisal or professional technical comparison

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not automatically send notices, complaints, filings, applications, or submit to any external system
- Must not automatically execute preservation, seizure and control, freezing, deduction, deletion, or other external operations
