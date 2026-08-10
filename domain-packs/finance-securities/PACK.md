# Finance & Securities Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for securities issuance and trading, information disclosure, suitability, and financial contracts
- Verification entry points for investor losses, trading chains, and regulatory identities

Excluded:

- Automatic determination of investment advice, return promises, licensing conclusions, market manipulation, or insider trading

## Official Sources

- [中华人民共和国证券法](https://www.npc.gov.cn/npc/c2/c30834/201912/t20191231_304436.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于审理证券市场虚假陈述侵权民事赔偿案件的若干规定](https://www.court.gov.cn/fabu/xiangqing/343221.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [最高人民法院关于证券市场虚假陈述侵权民事赔偿案件诉讼时效衔接适用相关问题的通知](https://gongbao.court.gov.cn/Details/76f7bf5d4aad36057dc65270dbbd0a.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Products and Transactions

Must ask:

- What are the product's legal form, issuer, seller, custodian, and investor identities?
- How did subscription, risk disclosure, suitability matching, and fund flows take shape?

Fact fields:

- Product structure
- Participating parties
- Transaction times
- Fund flows

Suggested evidence:

- Contracts, prospectuses, and risk disclosure statements
- Account statements, trade confirmations, and original audio/video recordings

Calculation hooks (only accepts confirmed rules and variables):

- Hand over only verified principal, cash flows, fees, and calculation rules to cn-calc; this pack does not calculate returns, losses, interest, or compensation amounts

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as subscription, redemption, risk disclosure, complaints, and dispute occurrence, and hand them to cn-deadline; this pack outputs no deadlines

Prohibited:

- Must not equate a product name with its legal nature, regulatory classification, or risk level
- Must not automatically determine that suitability obligations were breached, risk tolerance, or sales liability is established
- Must not automatically calculate principal, returns, fees, interest, losses, compensation, or any deadlines
- Must not provide investment advice, trade on behalf of clients, subscribe/redempt, transfer funds, complain, file, or perform other external operations

### Disclosure and Conduct

Must ask:

- Who disclosed or omitted the disputed information, when, and through which channel?
- What are the temporal and causal chain between the trading decision and the disputed information?

Fact fields:

- Disclosure-obligated parties
- Information content
- Publication time
- Trading decisions

Suggested evidence:

- Original announcements and official timestamps
- Trading records, communication records, and decision materials

Calculation hooks (only accepts confirmed rules and variables):

- Trade prices, quantities, and market data are only pending-verification cn-calc input; this pack does not select a loss model or output loss amounts

Deadline hooks (node identification only; no statutory deadlines computed):

- Register only candidate nodes such as implementation date, disclosure date, correction date, administrative proceedings, and trade dates, and hand them to cn-deadline; never automatically determine commencement or expiry dates

Prohibited:

- Must not automatically determine misrepresentation, materiality, inside information, manipulation, fault, or causation
- Must not automatically select benchmark dates, benchmark prices, loss models, or calculate compensation amounts
- Must not automatically determine the commencement, suspension, interruption, or expiry of limitation periods or other statutory deadlines
- Must not automatically trade, place orders, freeze accounts, publish announcements, complain, file, sue, or execute payment

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not automatically generate enforceable amounts, returns, losses, deadlines, or liability ratios
- Must not provide personalized investment advice or return promises, or execute trading, filing, litigation, payment, or other external operations
