# Data & Cyber Security Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for data processing activities, personal information, cyber security, cross-border transfers, and incident response
- Checklist of processing purposes, roles, data flows, systems, and third-party relationships

Excluded:

- Automatic determination of violations, automatic data deletion, automatic notification of regulators or data subjects, and executing network measures

## Official Sources

- [网络数据安全管理条例](https://www.cac.gov.cn/2024-09/30/c_1729384452307680.htm)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国网络安全法（2025年修正）](https://flk.npc.gov.cn/detail?fileId=&id=021e7d7684474107b8f3febbb1c4f8b5&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E7%BD%91%E7%BB%9C%E5%AE%89%E5%85%A8%E6%B3%95&type=)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国数据安全法](https://flk.npc.gov.cn/detail?fileId=&id=ff80818179f5e0800179f885c7e70392&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E6%95%B0%E6%8D%AE%E5%AE%89%E5%85%A8%E6%B3%95&type=)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国个人信息保护法](https://flk.npc.gov.cn/detail?fileId=&id=ff8081817b6472a3017b656cc2040044&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E4%B8%AA%E4%BA%BA%E4%BF%A1%E6%81%AF%E4%BF%9D%E6%8A%A4%E6%B3%95&type=)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Data Inventory and Processing Basis

Must ask:

- Which data are processed, which subjects are involved, and what are the purposes, systems, and lifecycle?
- What are the candidate roles of processors, entrusted parties, joint controllers, and recipients?

Fact fields:

- Data categories
- Processing purposes
- System locations
- Subjects and roles

Suggested evidence:

- Data dictionaries, flow diagrams, and system logs
- Privacy notices, consent records, and entrusted-processing agreements

Calculation hooks (only accepts confirmed rules and variables):

- Data volume, number of subjects, and number of systems are only pending-verification statistical inputs; this pack does not automatically trigger compliance conclusions, threshold judgments, or fine amounts

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as collection, authorization, withdrawal, deletion requests, retention, and policy versions, with explicit rule sources, and hand them to cn-deadline; this pack outputs no deadlines

Prohibited:

- Must not let the model select the lawful basis, processing role, important-data attributes, or consent on the user's behalf
- Must not automatically determine that processing is lawful, unlawful, necessary, excessive, or constitutes sensitive personal information, important data, or critical information infrastructure
- Must not automatically calculate data-volume thresholds, retention periods, response deadlines, fines, or compensation amounts
- Must not automatically collect, access, export, share, or delete data, consent on behalf of others, modify permissions, send notices, or file with regulators

### Security, Cross-Border Transfers, and Incidents

Must ask:

- Does the matter involve sensitive personal information, minors, important data, cross-border transfers, or large-scale processing?
- What are the incident discovery, scope, affected systems, containment measures, and evidence preservation?

Fact fields:

- Sensitive categories
- Cross-border links
- Incident timeline
- Scope of impact

Suggested evidence:

- Access logs, alerts, images, and response records
- Cross-border contracts, assessments, and recipient materials

Calculation hooks (only accepts confirmed rules and variables):

- Counts of affected records, subjects, systems, and regions are only pending-verification inputs; this pack does not automatically determine incident level, reporting obligations, or amounts

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as incident discovery, confirmation, containment, forensic collection, reporting, notification, and cross-border actions, and hand them to cn-deadline; this pack outputs no statutory deadlines

Prohibited:

- Must not automatically determine that a data breach, cyber security incident, unlawful cross-border transfer, or reporting/notification obligation occurred without verified facts
- Must not automatically determine incident level, data categories, scope of impact, cross-border paths, or the applicable regulator
- Must not automatically calculate affected counts, losses, fines, compensation, retention periods, reporting periods, or notification deadlines
- Must not automatically delete, isolate, disconnect networks, ban accounts, modify systems, access logs, file with regulators, notify individuals, or disclose externally

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not automatically generate enforceable data classifications, thresholds, amounts, deadlines, incident levels, or liability conclusions
- Must not perform access, export, sharing, deletion, isolation, network disconnection, banning, system modification, cross-border transmission, filing, or external notification
