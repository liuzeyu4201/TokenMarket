# Data Model：Usage Capture

## Capture

| 字段 | 约束 |
|------|------|
| cost_status | reported \| rated \| unresolved |
| settlement_basis | reported \| usage \| unresolved \| none |
| reported_cost_minor_units | 整数微单位或 null；未知禁止 0 |
| usage.* | 有则 ≥0 整数；缺失 null |
| parser_version | 非空 |
| evidence_digest | 标准化字段哈希 |
| unresolved_reason | 未决时必填 |

主键观察幂等：request_id。冲突载荷拒绝覆盖。
