# Real Estate & Construction Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for real estate transactions, development and construction, construction contracts, price settlement, and quality disputes
- Entry points for bidding, qualifications, variation orders, appraisal, and priority-payment issues

Excluded:

- Automatic conclusions on planning permits, administrative penalties, taxes and fees, and construction costs

## Official Sources

- [最高人民法院关于审理建设工程施工合同纠纷案件适用法律问题的解释（二）](https://www.court.gov.cn/zixun/xiangqing/504221.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国民法典](https://flk.npc.gov.cn/detail?id=ff808081729d1efe01729d50b5c500bf&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E6%B0%91%E6%B3%95%E5%85%B8)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Contracts, Bidding, and Qualifications

Must ask:

- Is bidding mandatory for the project, and what is the sequence of bidding and contract signing?
- What are the relationships among the employer, general contractor, subcontractor, actual constructor, and qualification use?

Fact fields:

- Project nature
- Bidding process
- Contract versions
- Qualification and subject chain

Suggested evidence:

- Bidding documents, award notices, and original contracts
- Qualification, subcontracting, site-management, and payment materials

Calculation hooks (only accepts confirmed rules and variables):

- Subjects, qualifications, and the contract chain are only structured factual inputs; this pack does not calculate discounted compensation, management fees, project prices, or liability amounts

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as bidding, contract conclusion, commencement/completion, site exit, rescission, and case acceptance, and hand them to cn-deadline; this pack outputs no deadlines

Prohibited:

- Must not skip quality, price, and actual performance review merely because a contract-invalidity candidate exists
- Must not automatically determine mandatory bidding, bid rigging, qualification borrowing, subcontracting, unlawful subcontracting, contract validity, or liable parties
- Must not automatically calculate project prices, discounted compensation, management fees, losses, liability ratios, or any deadlines
- Must not automatically send letters, stop work, exit the site, hand over the site, apply for appraisal, file leads, sue, enforce, or pay

### Price, Schedule, and Quality

Must ask:

- What are the scope of work, variation orders, pricing method, and settlement process?
- What are the facts of quality objections, repairs, appraisal, work stoppage, and schedule extensions?

Fact fields:

- Quantity of work
- Pricing agreement
- Variation orders
- Schedule and quality

Suggested evidence:

- Drawings, variation orders, progress payments, and settlement materials
- Acceptance, quality testing, repair, and schedule records

Calculation hooks (only accepts confirmed rules and variables):

- Hand over only verified contract price, quantities, variation orders, payments, and pricing rules to cn-calc; this pack does not select a costing methodology or output amounts

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as settlement submission, site exit, rescission, price maturity, demands, retention money, and priority-payment rights, with their sources, and hand them to cn-deadline; this pack outputs no deadlines

Prohibited:

- Must not let the model select the costing methodology, pricing standards, scope of judicial appraisal, or appraisal conclusions
- Must not automatically determine that quality is compliant, schedule extensions, changed circumstances (情势变更), priority-payment rights, or price liability are established
- Must not automatically calculate quantities, prices, retention money, repair costs, losses, interest, liability ratios, or deadlines
- Must not automatically apply for appraisal or preservation, send demands, discount, auction, sue, enforce, file, or pay

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not automatically generate enforceable quantities, costs, prices, deadlines, or liability ratios
- Must not perform work stoppage, site exit, handover, appraisal, preservation, demands, discount, auction, filing, litigation, enforcement, or payment
