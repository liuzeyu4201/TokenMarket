# Quickstart

```bash
cd services/proxy-gateway && go test -race ./internal/domain/passthrough/ -count=1
cd services/api-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_binding_lifecycle.py tests/unit/test_binding_http.py -q
```
