# Quickstart：原生透传内核

```bash
cd services/proxy-gateway && go test -race ./internal/domain/passthrough/ ./internal/httpserver/ -count=1
```

场景：三协议 golden body → 未知字段保留 → 平台 vs 上游错误 → 取消 ≤1s → 包内无 chatcompat。
