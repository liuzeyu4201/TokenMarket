# Quickstart：OpenAI 稳定数据面

```bash
cd services/proxy-gateway && go test -race ./internal/domain/passthrough/ -run OpenAI -count=1
```

可选真实冒烟（付费，需显式授权）：`TOKENMARKET_OPENAI_SMOKE=1 go test ./internal/domain/passthrough/ -run OpenAILiveSmoke -count=1`
