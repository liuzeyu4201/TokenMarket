# Quickstart

```bash
cd services/billing-service && PYTHONPATH=. uv run --locked --group dev pytest tests/unit/test_ledger.py -q
cd services/proxy-gateway && go test -race ./internal/domain/passthrough/ -count=1 -run Ledger
```
