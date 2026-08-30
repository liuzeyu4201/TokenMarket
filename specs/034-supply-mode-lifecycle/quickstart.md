# Quickstart：供给模式生命周期

```bash
cd services/api-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_connection_lifecycle.py tests/unit/test_connection_lifecycle_http.py -q
cd frontend && npm test -- --run src/pages/Connections.test.tsx
```

场景：上架锁定模式 → pause 立即 admits_new=false → 有绑定删除失败 → 共享池无 dedicated。
