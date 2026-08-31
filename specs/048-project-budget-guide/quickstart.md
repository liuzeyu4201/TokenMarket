# Quickstart

```bash
cd services/billing-service && PYTHONPATH=. uv run --locked --group dev pytest tests/unit/test_ledger.py tests/unit/test_overview.py -q
cd services/api-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_budget.py -q
cd frontend && npx vitest run src/pages/ProjectDetail.test.tsx
```
