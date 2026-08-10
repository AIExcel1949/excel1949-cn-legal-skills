# Competition & Antitrust Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for monopoly agreements, abuse of market dominance, concentration of undertakings, and unfair competition
- Preservation checklist for market, competitive-relationship, communication, and operating data

Excluded:

- Automatic determination of relevant market, dominance, monopoly conduct, trade-secret infringement, or filing obligations

## Official Sources

- [中华人民共和国反垄断法（2022年修正）](https://flk.npc.gov.cn/detail?fileId=&id=ff8081818234ccb501829f46c6ac2a5a&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%8F%8D%E5%9E%84%E6%96%AD%E6%B3%95&type=)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国反不正当竞争法（2025年修订）](https://www.npc.gov.cn/npc/c2/c30834/202506/t20250627_446247.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [国务院反垄断反不正当竞争委员会关于公用事业领域的反垄断指南](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fldzfys/art/2026/art_07d961f9da464c13b5030e7c273823c8.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Agreements and Market Power

Must ask:

- What are the participants, goods/services, geographic scope, transaction level, and competitive relationships?
- How did the agreements, communications, price/volume changes, and business justifications take shape?

Fact fields:

- Participating parties
- Goods and geography
- Competitive relationships
- Conduct timeline

Suggested evidence:

- Original contracts, meeting, email, and chat records
- Sales, price, customer, and substitutability data

Calculation hooks (only accepts confirmed rules and variables):

- Market share is only pending-verification data

Deadline hooks (node identification only; no statutory deadlines computed):

- Conduct duration and investigation nodes

Prohibited:

- Must not find a monopoly agreement from parallel conduct alone

### Unfair Competition

Must ask:

- What are the source and manner of use of the disputed marks, data, trade secrets, or promotional content?
- What evidence exists for secrecy, confidentiality measures, competitive relationships, and the chain of damage?

Fact fields:

- Subject matter of rights
- Access and use
- Confidentiality measures
- Market impact

Suggested evidence:

- Original carriers, permission logs, and confidentiality policies
- Promotional pages, transaction data, and customer feedback

Calculation hooks (only accepts confirmed rules and variables):

- Candidate ledger of losses and gains

Deadline hooks (node identification only; no statutory deadlines computed):

- Knowledge of infringement and evidence-preservation nodes

Prohibited:

- Must not automatically determine that information constitutes a trade secret or that promotion constitutes confusion

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not automatically send notices, complaints, filings, applications, or submit to any external system
- Must not automatically execute investigations, searches, preservation, seizure and control, or other external operations
