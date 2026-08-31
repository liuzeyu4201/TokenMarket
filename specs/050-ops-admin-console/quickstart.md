# Quickstart

```bash
cd services/admin-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_ops_catalog.py tests/unit/test_admin_rbac.py -q
cd frontend && npx vitest run src/admin
```
