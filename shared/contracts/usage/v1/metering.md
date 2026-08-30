# 计量策略：usage v1.1

目录 `metering_source` 映射：

| catalog | 结算 | 说明 |
|---------|------|------|
| `reported_cost` | reported 金额 | 无金额 → unresolved |
| `usage` | usage 维度（rated） | 无维度 → unresolved |
| `mixed` | 有金额则 reported，否则 usage | 两者都保留 |
| `none` | none | 不计量，禁止记 0 |
| `unresolved` | unresolved | 目录已声明无法确定 |

禁止用 0 表示未知。解析失败、负数、溢出、未知单位 → unresolved。
