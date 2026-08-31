# Data Model

## OpsPage

kind, items[], next_cursor, total, freshness live|stale|unknown

## ConfigDraft

draft_id, kind price|route, payload, status draft|simulated|approved|published|failed, active_unchanged

## Wizard

wizard_id, kind, impact[], status pending|confirmed|cancelled|expired, request_id
