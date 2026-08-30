# Phase 0 Research：买家 Project 生命周期

## Decision 1：扩展 `project/v1`，不新建 catalog 目录

**Decision**: 在 `shared/contracts/project/v1/project.openapi.yaml` 上 expand-only，版本 1.1.0。增加 list/PATCH/状态机/协议启用停用/删除/准入。PATCH 不含 `mode`，`additionalProperties: false`。

**Rationale**: SF01 已登记该契约；总纲禁止另起平行 Project 契约。

**Alternatives**: 新建 `buyer-project-lifecycle/v1/` — 与冻结 catalog 重复，拒绝。

## Decision 2：mode 双层不可变

**Decision**: 领域服务从不 UPDATE `mode`。PostgreSQL `BEFORE UPDATE` 触发器在 `NEW.mode IS DISTINCT FROM OLD.mode` 时抛完整性错误。HTTP 若请求体含 `mode` 返回 `MODE_IMMUTABLE`。

**Rationale**: SC-002 要求 API/UI/数据库均不能改 mode。

**Alternatives**: 仅应用层拒绝 — 运维 SQL 可改，弱于验收。

## Decision 3：创建声明协议 vs 创建后启用

**Decision**: 创建请求的 `enabled_protocols` 直接落库为 enabled，不查 Binding。创建后 `POST .../protocols/{protocol}/enable` 必须 `BindingLookup.has_enabled_binding`；SF11 前 `EmptyBindingLookup` 恒 False，因此启用失败关闭 `PROVIDER_BINDING_REQUIRED`。停用只改 `enabled`/`disabled_at`，不删行。

**Rationale**: 规格澄清：创建可声明集合；后续启用才强制 Binding。

**Alternatives**: 创建也查 Binding — 本 SF 将无法创建带协议的 Project，违反 US1。

## Decision 4：删除阻塞表与准入函数

**Decision**: `project_runtime_blockers(kind ∈ {key,in_flight_task,unsettled_ledger})`。后续 SF 写入；本 SF 删除时读取未解决行，有则 409 `DELETE_BLOCKED` 且 `data.blockers`。`allows_new_proxy(record)`：未删除且 `status==active` 才为 True。归档同一事务改 status，提交后直读即 False（满足 ≤1s，无缓存）。

**Rationale**: 规格要求本 SF 提供表与函数供网关/后续 SF 复用。

**Alternatives**: 本 SF 扫描尚不存在的 Key/账本表 — 空实现会误删，且耦合未落地实体。

## Decision 5：授权透镜与 IDOR

**Decision**: 每个写/读走会话 `workspace`。`effective_role != buyer` → 403 `FORBIDDEN_ROLE`。查找按 `(id, owner_account_id)`；他账号与未知 ID 均 `NOT_FOUND` +「资源不存在」。管理员不走本接口。

**Rationale**: SF09 已规定 UI 不是安全边界。

**Alternatives**: 404 vs 403 区分无权 — 可枚举 ID，拒绝。

## Decision 6：默认创建为 draft

**Decision**: `POST` 成功后 `status=draft`。`activate`：draft|suspended→active。`suspend`：active→suspended。`archive`：非 archived→archived。非法转换 409 且行不变。

**Rationale**: 状态机有 draft；创建立即 active 会跳过显式激活。
