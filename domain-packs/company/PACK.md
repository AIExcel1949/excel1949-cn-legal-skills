# Corporate Governance Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for company formation, capital system, governance bodies, and resolution procedures
- Issue identification for shareholder rights, director/supervisor/senior-manager duties, connected transactions, and corporate deadlock

Excluded:

- Final judgments on securities issuance, financial regulation, tax, and bankruptcy proceedings

## Official Sources

- [中华人民共和国公司法（2023年修订）](https://flk.npc.gov.cn/detail?fileId=&id=ff8081818c9108eb018cb6922f750c07&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%85%AC%E5%8F%B8%E6%B3%95&type=)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于适用《中华人民共和国公司法》时间效力的若干规定](https://gongbao.court.gov.cn/Details/868bf0fa625bd6082ab7595fe06fcc.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于《中华人民共和国公司法》第八十八条第一款不溯及适用的批复](https://gongbao.court.gov.cn/Details/152baf720b035b778662af0e0a8bd0.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Capital and Governance

Must ask:

- What are the shareholders' subscribed capital, paid-in capital, contribution deadlines, and contribution methods?
- How are powers allocated among the articles of association, shareholders' meeting, board of directors, and legal representative?

Fact fields:

- Equity structure
- Subscribed and paid-in capital
- Articles of association powers
- Governance bodies

Suggested evidence:

- Articles of association and all amendments
- Capital contribution flows, verification reports, and registration files

Calculation hooks (only accepts confirmed rules and variables):

- Hand over only verified contribution amounts, paid-in amounts, and ratio rules to cn-calc; this pack does not calculate or confirm amounts, differences, or equity ratios

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate trigger events such as contribution deadlines and meeting notices, with their rule sources, and hand them to cn-deadline; this pack outputs no deadlines

Prohibited:

- Must not determine actual capital contribution or control relationships from registration information alone
- Must not automatically determine the authority of decision-making bodies, validity of the articles of association, or validity of resolutions
- Must not automatically calculate contribution amounts, equity ratios, voting ratios, or any deadlines
- Must not sign resolutions on behalf of parties, automatically send meeting notices, handle registration, publication, disclosure, or payment

### Shareholder and Director/Supervisor/Senior-Manager Disputes

Must ask:

- Are the convening, notice, voting, and records of the disputed resolution complete?
- What are the objectives of disputes over information inspection, profit distribution, connected transactions, or control?

Fact fields:

- Resolution procedure
- Voting rights
- Affiliated relationships
- Damage and remedy objectives

Suggested evidence:

- Meeting notices, sign-in sheets, ballot papers, and minutes
- Financial books, connected transaction contracts, and fund flows

Calculation hooks (only accepts confirmed rules and variables):

- Provide only verified profits, losses, and distribution rules as cn-calc input; this pack does not calculate or confirm distributable amounts, losses, or liability ratios

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as resolution adoption, knowledge, notice, and filing suit, with the temporal-effectiveness authorities, and hand them to cn-deadline; this pack outputs no deadline conclusions

Prohibited:

- Must not automatically determine that resolutions are void, nonexistent, voidable, or that directors/supervisors/senior managers breached duties
- Must not automatically determine that affiliated relationships, causation, damage, or remedies are established
- Must not automatically calculate profit distribution, losses, compensation, liability ratios, or litigation deadlines
- Must not automatically file suit, send notices, inspect books, sign settlements, handle registration, or execute payment

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not automatically generate enforceable amounts, deadlines, liability ratios, or voting results
- Must not perform notices, signing, registration, publication, disclosure, litigation, payment, or other external operations
