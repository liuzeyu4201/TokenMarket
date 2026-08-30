# Phase 0 Research：连接验证与健康

## Decision 1：扩展 `provider-connection/v1` 至 1.2.0

**Decision**: expand-only 增加 verify、health、capabilities、内部健康快照。

## Decision 2：VendorProbe 端口 + 默认 fail-closed

**Decision**: 域内 `VendorProbe.probe(...)` 返回类别与发现列表。测试注入 ScriptedProbe。默认 `FailClosedProbe` 不发起网络。禁止创建文件/批任务。

## Decision 3：快照 = 发现 ∩ Catalog stable

**Decision**: 仅 `stability=stable` 且非 `control_plane` 的 provider+path_template。目录外路径丢弃。快照行版本递增。

## Decision 4：健康滞后与手动立即

**Decision**: 计划探测：成功连续 ≥2 → healthy；upstream_fault 连续 ≥3 → unhealthy；一次故障从 healthy → degraded。invalid/forbidden/region 立即 unhealthy。手动复验 `immediate=True` 一次成功即可 healthy。

## Decision 5：全局预算

**Decision**: `ProbeScheduler.tick` 最多处理 `probe_budget`（默认 8）条到期连接；`next_probe_at` 加间隔与抖动。1000 到期连接一次 tick 不得超过预算。
