# Data Model：连接健康与能力快照

## ProviderConnection（扩展）

| 字段 | 约束 |
|------|------|
| health_state | unknown \| healthy \| degraded \| unhealthy |
| health_reason | 脱敏类别/原因 |
| health_checked_at | timestamptz NULL |
| consecutive_successes / consecutive_failures | INT ≥0 |
| last_probe_at / next_probe_at | timestamptz NULL |
| capability_version | INT ≥0，当前快照版本 |

## CapabilitySnapshot

connection_id、version、capabilities JSON（protocol/path_template/model/region）、created_at。旧版本保留。

## ProbeAudit

owner、connection_id、category、health_state、request_id、source=manual\|scheduled。无明文、无完整 upstream body。

## HealthFact（供路由）

connection_id、health_state、reason、checked_at、capability_version、routable = healthy 且快照非空。
