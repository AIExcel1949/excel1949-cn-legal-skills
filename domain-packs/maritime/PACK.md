# Maritime Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for vessels, carriage of goods by sea, maritime compensation, general average, insurance, and foreign-related elements
- Materials checklist for bills of lading, electronic transport records, cargo damage, and liable parties

Excluded:

- Automatic conclusions on applicable law, limitation of maritime liability, general average adjustment, or foreign-related jurisdiction

## Official Sources

- [中华人民共和国海商法（2025年修订，自2026年5月1日起施行）](https://www.npc.gov.cn/npc/c2/c30834/202510/t20251028_449061.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于适用《中华人民共和国海商法》时间效力的若干规定（法释〔2026〕8号）](https://www.court.gov.cn/zixun/xiangqing/498581.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Carriage and Documents

Must ask:

- What are the shipper, carrier, actual carrier, consignee, and the cargo chain?
- How were the bill of lading or electronic transport record issued, endorsed, controlled, and delivered?

Fact fields:

- Transport parties
- Vessel and voyage
- Cargo and packing
- Transport documents

Suggested evidence:

- Contracts, bills of lading, electronic records, and cargo manifests
- Booking, handover, loading/unloading, and delivery records

Calculation hooks (only accepts confirmed rules and variables):

- Ledger of freight, demurrage, and cargo value

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate nodes for loading/unloading, delivery, notice, and limitation periods

Prohibited:

- Must not determine all contractual and proprietary relationships from document letterheads alone

### Maritime Accidents and Damage

Must ask:

- What are the accident time and place, vessel status, parties involved, and salvage and response?
- What is the evidence chain for cargo damage, collision, pollution, insurance, and third-party causes?

Fact fields:

- Accident process
- Vessel and personnel
- Damage items
- Insurance and salvage

Suggested evidence:

- Deck logs, VDR, AIS, and maritime investigation materials
- Survey reports, cargo evidence, and insurance claim materials

Calculation hooks (only accepts confirmed rules and variables):

- Hand over only manually confirmed loss, salvage, and limitation parameters to cn-calc to generate a candidate ledger

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate nodes for preservation of maritime claims and special limitation periods

Prohibited:

- Must not automatically determine collision liability ratios, applicable law, or limitation amounts

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not automatically send notices, maritime declarations, claims, preservation, or litigation applications, and must not submit to any external system
- Must not automatically arrest vessels, dispose of cargo, execute general average adjustment, or perform other external operations
