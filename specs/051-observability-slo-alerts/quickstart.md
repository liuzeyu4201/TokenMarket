# Quickstart

```bash
cd services/proxy-gateway && go test ./internal/observability/ ./internal/domain/passthrough/ -count=1
cd services/admin-service && PYTHONPATH=. uv run --locked --extra dev pytest tests/unit/test_slo.py -q
cd ops && uv run --project ../tools/workflow --locked pytest tests/test_slo_alerts.py -q
cd infra && uv run --project ../tools/workflow --locked pytest tests/test_grafana_provisioning.py -q
```
