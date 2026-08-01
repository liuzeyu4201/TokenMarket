# Convergence implement evidence (2026-08-01)

Automated suite (api-service):

```
uv run --locked --extra dev pytest \
  tests/unit/test_authorization*.py \
  tests/unit/test_route_exclude_self.py \
  tests/contract/test_authorization*.py \
  tests/integration/test_authorization*.py \
  tests/integration/test_route_exclude_api.py \
  tests/integration/test_ownership_change_visibility.py
→ 74+ passed (includes migration, evaluate matrix, SC-006 revoke, IDOR, audit, fail-closed)
```

SC mapping:

| SC | Evidence |
|----|----------|
| SC-001 | unit matrix + evaluate_api integration |
| SC-002 | unit test_route_exclude_self 1000x |
| SC-003 | test_authorization_role_live_read |
| SC-004a | test_authorization_performance (AUTHZ_PERF_BENCH) |
| SC-004c | fail_closed + audit fail unit |
| SC-005 | test_authorization_audit_persist |
| SC-006 | evaluate_api revoke → 401 |

Manual quickstart curl path optional when `make start` is up; automated path covers same scenarios via TestClient + testcontainers.
