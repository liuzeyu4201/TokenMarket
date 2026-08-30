# Quickstart：用量采集

```bash
cd services/proxy-gateway && go test -race ./internal/domain/usageparse/ ./internal/domain/passthrough/ -count=1
cd services/billing-service && PYTHONPATH=. uv run --locked --group dev pytest tests/unit/test_usage_observation.py -q
```
