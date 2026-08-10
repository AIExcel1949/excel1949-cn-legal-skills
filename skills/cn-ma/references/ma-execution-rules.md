# 并购交易执行矩阵口径

## 官方检索入口

以下法源并非每笔交易均适用。使用时须按交易结构、主体、行业、地域和时点逐项复核全文、效力、过渡规则及配套规定。

| 标识 | 法源 | 官方来源 | 效力信息 | 核验日期 |
|---|---|---|---|---|
| `company-law-2023` | 《中华人民共和国公司法（2023年修订）》 | [国家法律法规数据库](https://flk.npc.gov.cn/detail?fileId=&id=ff8081818c9108eb018cb6922f750c07&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%85%AC%E5%8F%B8%E6%B3%95&type=) | 数据库标示“有效”，2024年7月1日起施行 | 2026-07-18 |
| `anti-monopoly-law-2022` | 《中华人民共和国反垄断法》 | [国家法律法规数据库](https://flk.npc.gov.cn/detail?fileId=&id=ff8081818234ccb501829f46c6ac2a5a&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%8F%8D%E5%9E%84%E6%96%AD%E6%B3%95&type=) | 数据库标示“有效”，2022年8月1日起施行 | 2026-07-18 |
| `merger-filing-threshold-2024` | 《国务院关于经营者集中申报标准的规定》 | [国家市场监督管理总局](https://www.samr.gov.cn/fldes/jyzjzsbxbz/art/2024/art_eb4235b9a196486c8df15c7a61d51744.html) | 行政法规，2024年1月22日公布施行 | 2026-07-18 |
| `merger-review-2023` | 《经营者集中审查规定》 | [国家市场监督管理总局](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_4c34a8aa4e62449ab38233bdbba172a7.html) | 部门规章，2023年4月15日起施行 | 2026-07-18 |
| `foreign-investment-law` | 《中华人民共和国外商投资法》 | [国家法律法规数据库](https://flk.npc.gov.cn/detail?fileId=&id=ff8080816f135f46016f1d5318af145e&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%A4%96%E5%95%86%E6%8A%95%E8%B5%84%E6%B3%95&type=) | 数据库标示“有效” | 2026-07-18 |

## 输入边界

- `structure.confirmation_status` 必须忠实反映用户是否已确认结构；不得用行业惯例替代确认。
- `valuation_status` 只登记估值是否由有权人员确认或仍待确认，不要求脚本计算。
- 官方法源放入 `authority_sources`；意向书、协议草案、批复、清单等放入 `document_sources`。
- 所有执行事项的 `source_refs` 必须指向已登记来源，否则被阻断。

## 执行事项

- 审批：脚本保留 `required`、`not_required` 或 `to_be_determined`，不自行改变判断。
- 先决条件：仅按输入状态和证据要求追踪，不宣布满足。
- 陈述保证、承诺、赔偿：仅形成责任与来源矩阵，不接受或评价条款。
- 交割交付物：仅追踪责任人、依赖和证据，不执行签署、过户、付款或系统提交。
- 长停日期：仅保留显式日期或规则；不从含糊文本中推算。

## 依赖审计

每个事项 ID 在全矩阵中必须唯一。依赖必须指向已登记事项；出现自依赖、缺失依赖或环路时一律阻断，交律师重新编排。
