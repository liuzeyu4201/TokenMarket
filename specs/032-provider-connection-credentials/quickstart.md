# Quickstart：Provider Connection

```bash
cd services/api-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_connection_credentials.py tests/unit/test_connection_ssrf.py tests/unit/test_connection_http.py -q
cd frontend && npm test -- --run src/pages/Connections.test.tsx
```

场景：创建无明文 → SSRF 拒绝 → 内部 unwrap → 替换整包 → 删除后 unwrap 失败。
