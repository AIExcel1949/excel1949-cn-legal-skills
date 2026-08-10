# Environment & Ecology Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for construction projects, discharge permits, pollution incidents, ecological damage, and environmental administrative procedures
- Materials checklist for pollution sources, media, migration paths, monitoring, and causation

Excluded:

- Automatic determination of pollution liability, ecological damage, administrative violations, or remediation plans

## Official Sources

- [中华人民共和国生态环境法典（2026年8月15日起施行，核验日尚未施行）](https://www.moj.gov.cn/pub/sfbgw/zwgkztzl/2026nianzhuanti/2026qglh0206/lhsj20260206/202603/t20260312_532715.html)：核验状态 `not_yet_effective`，使用前必须再次核验。
- [中华人民共和国环境保护法（核验日现行，生态环境法典施行后应重新核验）](https://www.npc.gov.cn/zgrdw/npc/zfjc/zfjcelys/2016-10/26/content_1999801.htm)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Permits and Production Operations

Must ask:

- What are the project type, location, environmental impact assessment, permits, acceptance, and actual process?
- Are the discharge points, pollutants, treatment facilities, and operating records consistent?

Fact fields:

- Project and location
- Permit documents
- Process flow
- Discharges and facilities

Suggested evidence:

- EIA, approval, permit, and acceptance materials
- Production ledgers, online monitoring, and facility operation records

Deadline hooks (node identification only; no statutory deadlines computed):

- Permit, monitoring, rectification, and re-inspection nodes

Prohibited:

- Must not infer ongoing actual compliance from permit documents alone

### Pollution Incidents and Damage

Must ask:

- What are the chain of incident occurrence, discovery, spread, containment, and sampling?
- What evidence exists for the pollution source, migration path, receptors, damage, and other possible causes?

Fact fields:

- Incident timeline
- Polluted media
- Migration path
- Damaged subjects

Suggested evidence:

- On-site records, sample chains, and monitoring reports
- Meteorological/hydrological, production, and damage-assessment materials

Calculation hooks (only accepts confirmed rules and variables):

- Ledger of disposal costs and damage items

Deadline hooks (node identification only; no statutory deadlines computed):

- Reporting, sampling, preservation, and administrative remedy nodes

Prohibited:

- Must not infer the entire causal chain and damage scope from a single exceedance

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not automatically send notices, reports, permit applications, rectification reports, or submit to any external system
- Must not automatically halt production, dispose of pollutants, execute remediation plans, or perform other external operations
