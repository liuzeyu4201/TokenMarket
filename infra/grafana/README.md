# Grafana infrastructure assets

Dashboard and datasource provisioning templates. Runtime lifecycle of the local
Grafana container is owned by feature SF02 (`make dev` / `make start`).

Versioned V0.1 代理总览看板与 Prometheus 数据源位于
`infra/grafana/provisioning/`（含 `alerting/proxy.yaml` 自动加载到 Grafana 告警状态）。
Prometheus 规则位于 `ops/alerts/proxy.yml`。
全新环境通过这些文件重建，不依赖手工点击保存。缺失采集必须显示
No data，不得渲染为零。
