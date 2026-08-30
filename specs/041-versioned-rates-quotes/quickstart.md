# Quickstart：版本化费率

```bash
cd services/billing-service && PYTHONPATH=. uv run --locked --group dev pytest tests/unit/test_pricing.py -q
cd services/proxy-gateway && go test -race ./internal/domain/pricelock/ -count=1
```
