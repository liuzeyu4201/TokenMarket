# Evidence 049

`pytest tests/unit/test_admin_rbac.py tests/unit/test_admin_http.py tests/test_health.py` 16 passed. Combined coverage 87% (rbac 92%, service 93%). User cookie rejected at admin login. Full RBAC matrix asserted. High-risk without step-up/reason denied. Audit mutate/delete raise IMMUTABLE_AUDIT. Break-glass appends an alert and closes with review. credential.read / ledger.edit_balance never allowed.
