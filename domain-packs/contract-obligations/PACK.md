# Contract & Debt Obligations Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for contract formation (合同成立), effectiveness, performance, variation, rescission, and breach
- Identification of basic issues in sales, loan, and general services transactions
- Calculation entry points for principal, price, interest, liquidated damages, and loss items

Excluded:

- Final legal conclusions in special areas such as financial regulation, construction, maritime, and foreign-related contracts

## Official Sources

- [中华人民共和国民法典](https://www.moj.gov.cn/pub/sfbgw/zwgkztzl/2025nianzhuanti/2025mfdxcy/2025mfdxcy_mfdql/202505/t20250507_518708.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于审理买卖合同纠纷案件适用法律问题的解释](https://gongbao.court.gov.cn/Details/ba1b35d94fe5430b29f99395323878.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Formation & Validity

Must ask:

- When and how did the parties reach agreement (达成合意)?
- Do the contracting parties, agency authority, approvals/registration, or standard terms (格式条款) require verification?
- Are there disputed claims of invalidity, voidability, or pending validity (效力待定)?

Fact fields:

- Transaction parties
- Offer and acceptance process
- Signing time and method
- Agency and authorization
- Contract versions and annexes

Suggested evidence:

- Original contract and version hashes
- Authorization documents and party registration information
- Negotiation emails, chats, and signing records

Deadline hooks (node identification only; no statutory deadlines computed):

- Candidate nodes for exercising the right to rescind or terminate
- Candidate facts for the commencement of the limitation period (诉讼时效)

Prohibited:

- Must not determine the nature of the legal relationship from the contract title alone

### Performance & Breach

Must ask:

- What are the content and sequence of the main obligations, ancillary obligations, and cooperation duties?
- When did performance, rejection of goods, quality objections, demands, and remedies each occur?
- What factual basis exists for the counterparty's defenses of setoff, concurrent performance, or prior performance?

Fact fields:

- Delivery content
- Acceptance and objections
- Payment milestones
- Demands and notices
- Performance obstacles

Suggested evidence:

- Delivery notes, acceptance sheets, statements of account, and invoices
- Payment flows and purpose statements
- Notice-service vouchers and correspondence

Calculation hooks (only accepts confirmed rules and variables):

- Principal or price balance
- Interest, liquidated damages, and loss line items

Deadline hooks (node identification only; no statutory deadlines computed):

- Payment due dates
- Candidate inspection or objection periods

Prohibited:

- Must not treat an invoice alone as sufficient proof of contract formation or payment

### Rescission and Remedies

Must ask:

- Are the goals of claiming rescission, continued performance, repair/rework, or damages conflicting?
- Was the rescission notice sent, when did it arrive, and was it objected to?
- What are the causal chain and mitigation between the loss items and the breach?

Fact fields:

- Remedy objectives
- Grounds for rescission
- Notice and arrival
- Replacement transactions
- Losses and mitigation

Suggested evidence:

- Rescission or demand notices and service vouchers
- Replacement purchase, resale, or repair materials
- Loss vouchers and causation materials

Calculation hooks (only accepts confirmed rules and variables):

- Itemized ledger of loss items
- Refund and setoff of amounts paid

Deadline hooks (node identification only; no statutory deadlines computed):

- Arrival date of the rescission notice
- Candidate limitation periods for filing suit or arbitration

Prohibited:

- Must not double-count mutually incompatible remedy items

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
