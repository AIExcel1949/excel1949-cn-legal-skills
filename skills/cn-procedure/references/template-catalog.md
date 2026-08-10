# 模板目录与选择规则

## 核心模板

| 模板标识 | 文件 | 适用场景 |
|---|---|---|
| `civil-firm-letter` | `01-所函/所函（民事）.docx` | 民事案件律所致法院所函 |
| `criminal-firm-letter` | `01-所函/所函（刑事）.docx` | 刑事案件律所致办案机关所函 |
| `civil-power-attorney` | `02-授权委托书/授权委托书（民事-特别授权）.docx` | 民事律师代理，授权事项逐项填写 |
| `civil-relative-power-attorney` | `02-授权委托书/授权委托书（民事-亲属关系）.docx` | 符合法定范围的公民代理 |
| `civil-organization-employee-power-attorney` | `02-授权委托书/授权委托书（民事-单位工作人员）.docx` | 法人或非法人组织委托本单位工作人员；权限逐项填写 |
| `criminal-power-attorney` | `02-授权委托书/授权委托书（刑事）.docx` | 刑事辩护或代理，须明确阶段 |
| `administrative-power-attorney` | `02-授权委托书/授权委托书（行政）.docx` | 行政诉讼代理 |
| `civil-engagement` | `03-委托代理合同/委托代理合同（民事-一般代理）.docx` | 民事一般代理 |
| `civil-risk-engagement` | `03-委托代理合同/委托代理合同（民事-风险代理）.docx` | 允许风险代理的民事财产事项 |
| `criminal-engagement` | `03-委托代理合同/委托代理合同（刑事）.docx` | 刑事分阶段委托 |
| `administrative-engagement` | `03-委托代理合同/委托代理合同（行政）.docx` | 行政代理 |
| `enforcement-engagement` | `03-委托代理合同/委托代理合同（执行）.docx` | 执行阶段代理 |
| `legal-advisor` | `04-法律顾问合同/法律顾问合同（常年）.docx` | 常年法律顾问，不加入诉讼默认包 |
| `intake-approval` | `05-审批表/审批表-收案.docx` | 收案、利益冲突和收费审批 |
| `criminal-intake-approval` | `05-审批表/审批表-收案（刑事）.docx` | 刑事收案、委托关系、利益冲突和收费审批 |
| `seal-approval` | `05-审批表/审批表-用章.docx` | 用章审批 |
| `closure-approval` | `05-审批表/审批表-结案.docx` | 结案、结算和归档审批 |
| `approval-summary` | `05-审批表/审批表-三合一.docx` | 汇总查看，不替代独立审批记录 |

## 加强版模板

`references/加强版/` 含律所内部管理、补充与解除协议、当事人端申请书、身份证明和协议底稿。它们默认不进入批量文书包，因为每份文书的事实门槛和法律判断不同。

已登记的申请书标识包括：`protective-order-application`、`change-claims-application`、`enforcement-application`、`withdrawal-application`、`property-preservation-application`、`release-preservation-application`、`online-enforcement-search-application`。

已登记的身份证明标识包括：`legal-representative-certificate`、`organization-employee-certificate`。工作人员身份证明仅证明劳动或人事关系，不能替代授权委托书。

优先按用户明确请求选择单份模板。涉及人身安全保护令、财产保全、强制执行、撤诉、解除合同、利益冲突豁免或案件转所时，必须先收集专门事实，不得只依赖通用案件 JSON。

## 不应合并的边界

- 常年法律顾问合同与诉讼委托合同分开。
- 律所内部审批表与法院提交材料分开。
- 诉状、答辩状和证据目录由其他 Skill 负责；本 Skill 不重复生成。
- 实体争议分析、法条检索和类案检索由独立 Skill 负责；本 Skill 只消费已核验结论。
