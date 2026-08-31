# Data Model

## Tenant

buyer_id, project_id, key_id, protocol；种子 `20260831`，n=500。

## Reservation

request_id, project_id, amount, state open|settled|aborted；结束时 open=0。

## RunReport

profile, tenants, target_rps, achieved_rps, duration, total, success, success_rate, platform_p95_ms, disconnect_rate, heap_delta_bytes, open_reservations, double_charge, cross_tenant_leaks, pass
