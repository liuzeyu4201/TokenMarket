# Phase 0 Research：Provider Binding

## Decision 1：独立 `provider-binding/v1` 契约

**Decision**: 新目录，不塞进 `project/v1`。Project 仍是根；Binding 是其协议配置。

**Rationale**: SF01 已预留独立领域契约风格；expand project OpenAPI 会把生命周期与供给配置缠死。

**Alternatives**: 扩 project/v1 — 拒绝，契约边界不清。

## Decision 2：单 active 用部分唯一 + 行锁

**Decision**: `UNIQUE (project_id, protocol) WHERE status = 'active'`。发布事务先锁 `(project_id, protocol)` 再将旧 active 置 inactive、新行 active。冲突 → 409。

**Rationale**: SC-002 并发只一胜；Postgres 约束兜底。

**Alternatives**: 仅应用层 CAS — 竞态可双活。

## Decision 3：已发布行不可变

**Decision**: publish 后不得 UPDATE 配置列。变更 = 新草稿再发布。旧 version 行保留供在途锁定。

**Rationale**: 「请求锁定 version；修改只影响后续请求」。

## Decision 4：Connection / 价格端口

**Decision**: `ConnectionLookup` 默认空 → 专享发布 `CONNECTION_REQUIRED`。`PriceAvailability`：该协议在冻结目录中存在 stable 且非 control_plane 的数据面记录则通过。测试可注入 Connection 事实。

**Rationale**: SF14/SF27 未落地；不得伪造健康或价格。

**Alternatives**: 发布跳过校验 — 违反 FR-005。

## Decision 5：degraded 不回退

**Decision**: `degrade_for_connection` 将引用该 connection 的 active dedicated 改为 degraded。`admit` 对 degraded 失败关闭，不改 supply_mode、不创建 shared Binding。

**Rationale**: 总纲禁止专享自动故障转移到共享池。

## Decision 6：替换 EmptyBindingLookup

**Decision**: `BindingService.has_enabled_binding` 在 status∈{active,degraded} 时为 True，供 SF10 启用协议。准入仍要求 active。
