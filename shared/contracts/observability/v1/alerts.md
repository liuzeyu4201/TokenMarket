# 告警目录

每条告警必须含：kind、影响、阈值、dashboard、runbook、owner、升级路径。

| kind | 阈值 | owner | 升级 |
|------|------|-------|------|
| upstream_slow | p95 > 2s | proxy-gateway | P1 on-call |
| no_candidate | 计数 > 0 | proxy-gateway | P1 on-call |
| event_backlog | 深度 > 1000 | proxy-gateway | P1 on-call |
| unresolved_spike | 15 分钟增量 > 10 | billing-service | P1 finance/ops |
| connection_unhealthy | unhealthy > 0 | supply_ops | P1 supply |

Runbook：`ops/runbooks/slo-alerts.md`。Dashboard：`v02-slo-overview`。
错误预算告警：`error_budget_low` 当 freeze_release。
