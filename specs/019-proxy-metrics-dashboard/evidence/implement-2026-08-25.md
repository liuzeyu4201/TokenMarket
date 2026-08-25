# Implement 2026-08-25

- Metrics: `proxy_requests_total`, `proxy_request_duration_seconds`, `provider_key_inventory`, `provider_usage_observe_total`, `provider_health_check_total` (bounded labels).
- Dashboard: `infra/grafana/provisioning/dashboards/v01-proxy-overview.json` (refresh 10s, No data on scrape miss).
- Alert: `ops/alerts/proxy.yml` system error rate >5% / ≥20 samples / 5m; recover <3%; excludes client 4xx.
- Tests: `internal/observability/chat_metrics_test.go`, `infra/tests/test_grafana_provisioning.py`, `ops/tests/test_proxy_alerts.py`.
