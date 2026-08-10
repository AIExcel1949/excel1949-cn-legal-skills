# Bankruptcy & Restructuring Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Organization of bankruptcy petitions, claim filings, assets and liabilities, avoidance and recovery, reorganization, and distribution matters
- Materials checklist for debtors, creditors, administrators, and security relationships

Excluded:

- Automatic determination of bankruptcy grounds, distribution priority, voting results, or reorganization feasibility

## Official Sources

- [中华人民共和国企业破产法](https://flk.npc.gov.cn/detail?id=2c909fdd678bf17901678bf63c7c0343&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E4%BC%81%E4%B8%9A%E7%A0%B4%E4%BA%A7%E6%B3%95)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于适用《中华人民共和国企业破产法》若干问题的规定（一）](https://gongbao.court.gov.cn/Details/3d2d4ab54101faca18768de8d15e87.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于适用《中华人民共和国企业破产法》若干问题的规定（二）](https://gongbao.court.gov.cn/Details/a8cf0deff0d638a2fad2bc64677f6f.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于适用《中华人民共和国企业破产法》若干问题的规定（三）](https://pccz.court.gov.cn/pcajxxw/pcFlfg/flfgxq?id=5437373E35A5ACC13981864FB88845B8)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Petition and Claim Filing

Must ask:

- What materials exist on the petitioner, due debts, assets and liabilities, and solvency status?
- What are the principal amount, nature, security, litigation/enforcement, and filing status of each claim?

Fact fields:

- Petitioning party
- Assets and liabilities
- Claim ledger
- Security and enforcement

Suggested evidence:

- Financial statements, collection and enforcement materials
- Contracts, judgments, security instruments, and filing vouchers

Calculation hooks (only accepts confirmed rules and variables):

- Hand over only verified principal, interest accrual cutoff dates, setoffs, security, and calculation rules to cn-calc; this pack does not confirm claim amounts, nature, or priority

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as petition acceptance, claim filing, review objections, and creditors' meetings, plus explicit dates in court documents, and hand them to cn-deadline; this pack outputs no statutory deadlines

Prohibited:

- Must not find bankruptcy grounds based on a single non-payment, a termination-of-enforcement order, or a single financial document
- Must not automatically confirm claims, security validity, claim nature, priority, or the existence of setoff rights
- Must not automatically calculate claims, interest, payment amounts, voting amounts, recovery rates, or filing/objection deadlines
- Must not automatically submit bankruptcy petitions or claim filings, vote on behalf of creditors, sign documents, dispose of property, distribute, or pay

### Debtor Property and Reorganization

Must ask:

- What were the pre-petition transactions, affiliated relationships, preferential payments, and property outflows?
- Are the inputs on going-concern value, financing, class voting, and recovery scenarios verifiable?

Fact fields:

- Pre-petition transactions
- Affiliated relationships
- Property changes
- Operating and reorganization assumptions

Suggested evidence:

- Bank statements, general ledgers, and material contracts
- Asset appraisals, operating data, and reorganization plan versions

Calculation hooks (only accepts confirmed rules and variables):

- Hand over only lawyer-confirmed asset, claim, class, and scenario rules to cn-calc; this pack does not generate recovery plans, valuations, recovery rates, or feasibility conclusions

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as pre-petition transactions, administrator knowledge, avoidance and recovery, reorganization plan submission, and voting, and hand them to cn-deadline; this pack outputs no deadlines

Prohibited:

- Must not automatically determine that transactions are avoidable, void, preferential, affiliated, recoverable, or that reorganization plans are feasible
- Must not automatically determine property ownership, claim classes, voting results, cram-down conditions, distribution priority, or administrator liability
- Must not automatically calculate valuations, recovery amounts, payment amounts, recovery rates, voting amounts, liability ratios, or any deadlines
- Must not automatically recover or dispose of assets, send notices, submit plans, vote on behalf of creditors, apply for approval, distribute, or pay

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not automatically generate enforceable claim amounts, valuations, recovery rates, voting results, deadlines, or liability ratios
- Must not perform petitions, filings, notices, voting, recovery, disposition, signing, reorganization-plan submission, distribution, or payment
