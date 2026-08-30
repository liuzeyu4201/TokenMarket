# Quickstart：流与亲和

```bash
cd services/proxy-gateway && go test -race ./internal/domain/passthrough/ ./internal/domain/affinity/ ./internal/httpserver/ -count=1
```

全量 soak（可选）：`TOKENMARKET_SOAK_SSE=500 TOKENMARKET_SOAK_DURATION=2h go test -race ./internal/domain/passthrough/ -run Soak -count=1`
