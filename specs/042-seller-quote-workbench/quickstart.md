# Quickstart：卖家工作台

```bash
cd services/api-service && PYTHONPATH=. uv run --locked --group dev pytest tests/unit/test_workbench.py tests/unit/test_workbench_http.py -q
cd frontend && npm test -- src/pages/Supply.test.tsx
```
