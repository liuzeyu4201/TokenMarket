# Quickstart

```bash
uv run --project tools/workflow pytest tests/workflow/test_release_gate.py tests/workflow/test_v02_invariants.py -q
cd services/api-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_release_buyer_journey.py -q
cd frontend && npx vitest run src/release src/admin/Catalog.test.tsx src/pages/Home.test.tsx src/pages/Login.accessibility.test.tsx
```
