# Consumer & Advertising Domain Pack

Author: AIOffice职场通关-excel1949  Status: testing  Official-source verification date: 2026-07-18

This pack is a problem-identification and material-organization component. It is NOT a standalone Skill and does NOT replace `cn-research` statutory verification.

## Scope

- Fact organization for consumer transactions, product/service quality, platform liability, promotional materials, and after-sales handling
- Checklist of advertising subjects, media, content, approvals, and evidence retention

Excluded:

- Automatic determination of fraud, false advertising, punitive damages, or administrative violations

## Official Sources

- [中华人民共和国消费者权益保护法](https://www.npc.gov.cn/npc/c2/c12435/c12488/201905/t20190521_184603.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [中华人民共和国广告法（2021年修正）](https://flk.npc.gov.cn/detail?id=ff8081817ab231eb017abd6bd860052d&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%B9%BF%E5%91%8A%E6%B3%95)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [《中华人民共和国广告法》适用问题执法指南（一，2025年发布）](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/ggjgs/art/2026/art_75bdff5f79d047d287f795c205c78d3b.html)：核验状态 `effective_at_verification`，使用前必须再次核验。
- [广告引证内容执法指南（2026年发布）](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/ggjgs/art/2026/art_8962fc1e4eb44a87b93d265af43b6940.html)：核验状态 `effective_at_verification`，使用前必须再次核验。

## Question Families

### Transactions and Quality

Must ask:

- What were the purchase purpose, transaction parties, goods/services, payment and delivery, and after-sales process?
- What materials exist on defects, damage, testing, repair/return/exchange, and platform intervention?

Fact fields:

- Transaction parties
- Goods/services
- Quality performance
- After-sales process

Suggested evidence:

- Orders, payment, invoice, and logistics materials
- Physical goods, test, repair, and customer-service records

Calculation hooks (only accepts confirmed rules and variables):

- Ledger of price, losses, and refunds

Deadline hooks (node identification only; no statutory deadlines computed):

- Problem discovery, notice, and after-sales nodes

Prohibited:

- Must not find fraud against the business operator from consumer complaints alone

### Advertising and Marketing Review

Must ask:

- Who created, reviewed, and published the content, and to what audience and media?
- What are the evidentiary basis, conditions and limitations, and dynamic page versions for the claims?

Fact fields:

- Advertising subjects
- Publication channels
- Promotional claims
- Review basis

Suggested evidence:

- Page snapshots, ad-backend and version records
- Test reports, approval documents, and authorization materials

Deadline hooks (node identification only; no statutory deadlines computed):

- Fact-node candidates for publication, takedown, and regulatory communication; no automatic communication

Prohibited:

- Must not find advertising violations without verifying context, audience, and evidence

## Global Boundaries

- Must not present the question checklist as established legal conclusions
- Must not skip verification of jurisdiction, temporal effectiveness, procedural stage, and local rules
- Must not fabricate facts the party did not state and the materials cannot support
- Must not use model-generated amounts, deadlines, or liability ratios directly for submission
- Must not automatically send notices, complaints, reports, takedown instructions, or submit to any external system
- Must not automatically delete advertisements, withdraw products, deduct, refund, or execute other external operations
