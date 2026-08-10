# 输入数据契约

## 1. 顶层字段

- `schema_version`：固定为 `1.0`。
- `matter`：仅填写脱敏的案件标识和名称。
- `as_of_date`：本次计算的核验基准日，格式为 `YYYY-MM-DD`。
- `input_confirmed_by_lawyer`：只有律师已确认本次全部输入时才能为 `true`。该字段不表示律师已审查输出。
- `benchmarks`：基准、合同条款、凭证、裁判文书或人工指令的来源记录。
- `variables`：公式可使用的输入变量。
- `calculations`：按顺序执行的计算项目。

## 2. 基准来源

每条来源必须包含：

- 稳定 `id`、来源类型、标题、具体定位和与计算直接相关的原文摘录；
- `verification_status: verified`和不晚于 `as_of_date` 的 `verified_on`；
- `applicability_status: confirmed_for_calculation`，表示律师已确认该来源可用于本次计算；
- `locator`：可为页码、条款、证据编号、存储路径或可回查 URL，不得只写「网络」、「法律」等模糊词。

脚本只检查这些声明是否完整，不证明来源内容实际真实或法律适用结论正确。

## 3. 变量

### 十进制字面量

```json
{
  "id": "principal",
  "label": "本金",
  "kind": "decimal",
  "value": "100000.00",
  "unit": "money",
  "currency": "CNY",
  "source_ids": ["contract_principal"]
}
```

`value` 不允许科学计数法、千分位或货币符号。

### 有理数

```json
{
  "id": "annual_rate",
  "label": "年比例",
  "kind": "rational",
  "numerator": "6",
  "denominator": "100",
  "unit": "ratio",
  "source_ids": ["contract_rate"]
}
```

分母必须为正整数。比例不自动理解为百分数；`6/100` 与 `6` 含义不同。

### 日期期间

```json
{
  "id": "interest_days",
  "label": "计息日数",
  "kind": "date_span",
  "start_date": "2025-01-02",
  "end_date": "2025-02-01",
  "include_start": false,
  "include_end": true,
  "unit": "calendar_day",
  "source_ids": ["period_instruction"]
}
```

天数按日历日计算：先取起止日期之差，再按两个布尔字段确定是否计入边界日。

## 4. 计算项

- `formula`：仅使用变量 ID、排在本项之前的计算 ID、整数常量和受限四则运算。小数和比例应放在变量中。
- `result_type`：`money` 或 `quantity`。金额结果必须给出 `currency`，数量结果必须给出 `unit`。
- `rounding.quantum`：显式舍入量级，例如 `0.01`、`1`、`100`。
- `rounding.mode`：`HALF_UP`、`HALF_EVEN`、`DOWN`、`UP`、`FLOOR` 或 `CEILING`。
- `source_ids`：支持本项公式选择、参数组合或汇总关系的来源。

引用前序金额结果时，本项币种必须与被引用结果一致。脚本不会用未舍入中间值替换前序结果；公式引用的是前序项的舍入后值，以保持对账可见性。

引擎同时检查基本量纲。`ratio` 是无量纲，`calendar_day` 与 `day` 视为同一日数量纲；其他单位保持独立。例如「金额 × 比例 × 日数 ÷ 年基准日数」的结果量纲为金额，但「金额 ＋ 比例」会被阻断。
