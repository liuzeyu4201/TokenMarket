# Implement 2026-08-25 (SF19 Grafana mount)

- `compose.local.yml` bind-mounts `./grafana-provisioning` → `/etc/grafana/provisioning` (read-only).
  SF02 stdin project dir is staged by `ComposeAdapter._stage_grafana_provisioning`.
- `compose.middleware.yml` bind-mounts `../grafana/provisioning`.
- Datasource URL is `http://host.docker.internal:9090` (not Grafana-container localhost).
- `provider_key_inventory` is registered in the gateway process and published from `pool.Snapshot()` on refresh.
- `provider_health_check_total` increments from `keyhealth.Scheduler.OnProbe`.
