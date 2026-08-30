# Quickstart：Project 代理 Key

```bash
cd services/api-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_project_proxy_keys.py tests/unit/test_proxy_keys.py -q
cd services/proxy-gateway && go test ./internal/domain/proxyauth/ -count=1
cd frontend && npm test -- --run src/pages/ProjectDetail.test.tsx
```

场景：签发一次明文 → 列表无明文 → 协议/IP/额度拒绝 → 撤销 1s 内失败 → 跨 Project 404。
