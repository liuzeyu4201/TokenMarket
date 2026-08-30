# Quickstart：连接验证与健康

```bash
cd services/api-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_connection_health.py tests/unit/test_connection_verify_http.py -q
cd frontend && npm test -- --run src/pages/Connections.test.tsx
```

场景：六类探测结果 → 快照仅目录内 → 单次故障不 unhealthy → 1000 连接 tick ≤ 预算 → 手动复验恢复 → 响应无 secret。
