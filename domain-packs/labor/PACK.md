# Labor & Employment Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for labor relationships, formation and performance, wages and working hours, termination, and non-compete restrictions
- Identification of arbitration precedence, limitation periods, and employment-subject candidates
- Calculation entry points for wages, compensation, and damages items

Excluded:

- Final conclusions on work-injury recognition and benefits, social insurance administrative disputes, seafarer labor, and cross-border employment

## Official Sources

- [中华人民共和国劳动合同法](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于审理劳动争议案件适用法律问题的解释（二）](https://gongbao.court.gov.cn/Details/bb72019c45453f84d920bd6375573e.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Labor Relationship and Employment Subject

Must ask:

- Who recruited, managed, paid wages, paid social insurance, and provided working conditions?
- Do affiliated companies, outsourcing, subcontracting, affiliation (挂靠), dispatch, or platform work exist?
- Is the written contract consistent with actual employment?

Fact fields:

- Recruiting subject
- Managing subject
- Wage payments
- Social insurance contributions
- Contract vs. actual employment

Suggested evidence:

- Labor contracts, offer, and onboarding materials
- Attendance records, work instructions, and account permissions
- Wage flows, individual income tax, and social insurance records

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate hire and departure dates
- Candidate commencement of the arbitration limitation period

Prohibited:

- Must not exclude the actual employment subject based on the contract letterhead alone

### Wages, Working Hours, and Benefits

Must ask:

- What are the wage structure, pay period, payment records, and disputed months?
- Which working-hour system applies, and do approvals or special working-hour documents exist?
- How do overtime facts, employer-held records, and the worker's own records corroborate each other?

Fact fields:

- Wage structure
- Pay period
- Working-hour system
- Attendance and overtime
- Leave and benefits

Suggested evidence:

- Pay slips, bank flows, and individual income tax records
- Attendance, scheduling, approval, and work-output records
- Rules and regulations and their publication/service materials

Calculation hooks (only accepts confirmed rules and variables):

- Month-by-month wage arrears ledger
- Manually confirmed inputs for overtime hours and calculation rules

Deadline hooks (node identification only; no statutory deadlines computed):

- Wage payment cycle
- Candidate nodes for continuing violations and termination

Prohibited:

- Must not automatically determine all overtime from message timestamps in chats alone

### Termination and Non-Compete

Must ask:

- Who proposed termination, when, on what grounds, and when did the notice arrive?
- Are the policy, procedure, evidence, and trade-union steps on which the grounds rely complete?
- What are the non-compete subjects, secret exposure, scope, term, and compensation performance?

Fact fields:

- Terminating party and grounds
- Notice service
- Policy and procedure
- Years of service
- Non-compete agreement and performance

Suggested evidence:

- Termination notices and service vouchers
- Rules and regulations, democratic procedure, and publication materials
- Performance, discipline, or consultation records
- Non-compete agreements, secret exposure, and compensation flows

Calculation hooks (only accepts confirmed rules and variables):

- Candidate items for economic compensation or damages
- Ledger of non-compete compensation and liquidated damages

Deadline hooks (node identification only; no statutory deadlines computed):

- Arrival date of the termination notice
- Arbitration application date and limitation candidates

Prohibited:

- Must not automatically treat the employer's written grounds as true, lawful, and procedurally complete

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
