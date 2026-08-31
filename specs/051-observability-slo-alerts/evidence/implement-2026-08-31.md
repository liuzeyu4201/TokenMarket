# Evidence 051

Go `go test ./internal/observability/ ./internal/domain/passthrough/ ./internal/httpserver/` passed. SLO 指标有界标签；user_id 拒绝；平台/upstream 直方图分离；无候选计数；SSE first_event；透传失败关闭时 `proxy_route_no_candidate_total` 增加。

admin-service `pytest tests/unit/test_slo.py` 6 passed。domain/slo 覆盖率 99%。五段 hop 串联；异步 usage/ledger 为 link；数据面 9995/10000 不冻结，管理面预算烧尽 freeze；五类告警阈值；脱敏扫描测试 secret 命中后被 redact；HTTP `/admin/v1/slo` 需 alert.read。

ops `tests/test_slo_alerts.py` 4 passed；infra Grafana v02 仪表盘 4 passed（含既有 v01）。契约目录登记 `observability/v1` 1.0.0。
