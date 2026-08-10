# Criminal Defense Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Organization of procedural nodes, alleged facts, and evidence lists across investigation, review-for-prosecution, and trial stages
- Entry points for organizational crimes, property disposition, leniency for admitting guilt and accepting punishment (认罪认罚), and defense materials

Excluded:

- Conviction/sentencing predictions, evading investigation, fabricating evidence, contacting witnesses, or making guilty-plea decisions on the client's behalf

## Official Sources

- [中华人民共和国刑事诉讼法（2018年修正）](https://flk.npc.gov.cn/detail?fileId=&id=ff8080816f135f46016f1d1b81b01351&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%88%91%E4%BA%8B%E8%AF%89%E8%AE%BC%E6%B3%95&type=)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国刑法修正案（十二）（自2024年3月1日起施行）](https://www.npc.gov.cn/npc/c2/c30834/202312/t20231229_433988.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Procedure and Protection of Rights

Must ask:

- Which stage is the case in, what coercive measures were taken, and when was service made?
- Are the materials on meetings, case-file review, applications, notifications, and the leniency procedure complete?

Fact fields:

- Case stage
- Coercive measures
- Service and notification
- Exercise of defense rights

Suggested evidence:

- Legal documents, service and meeting records
- Case-file review lists, applications, and replies

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate nodes for detention, review, trial, and remedies

Prohibited:

- Must not compute criminal procedural deadlines without verified rules and starting facts

### Alleged Facts and Evidence

Must ask:

- How are the alleged conduct, time and place, subject identity, and mental elements expressed?
- What contradictions exist among testimonial evidence, physical evidence, electronic data, appraisals, and fund chains?

Fact fields:

- Alleged conduct
- Subject and identity
- Evidence list
- Favorable and unfavorable facts

Suggested evidence:

- Original prosecution recommendation or indictment
- Transcripts, original electronic data, appraisal reports, and seizure lists

Calculation hooks (only accepts confirmed rules and variables):

- Amounts involved are calculated only as a side channel from confirmed data

Deadline hooks (node identification only; no statutory deadlines computed):

- Evidence application and cross-examination (质证) nodes

Prohibited:

- Must not predict conviction or sentencing, or instruct on destroying, concealing, or fabricating evidence

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not automatically contact witnesses, judicial authorities, or other external persons, and must not automatically submit defense, application, or complaint materials
- Must not automatically delete, conceal, transfer, or alter evidence, or execute other external operations
