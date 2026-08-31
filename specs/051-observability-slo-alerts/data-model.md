# Data Model

## TraceHop

request_id, service, stage (proxy|route|upstream|usage|ledger), kind (span|link), freshness live|stale|unknown, at

## SLOSnapshot

plane dataplane|admin, target, window_seconds, good, total, availability, error_budget, remaining_ratio, freeze_release

## AlertInstance

kind upstream_slow|no_candidate|event_backlog|unresolved_spike|connection_unhealthy, firing, threshold, impact, dashboard, runbook, owner, escalation
