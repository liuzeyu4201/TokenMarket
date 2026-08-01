# Data Model：角色授权与自买自卖隔离

**Feature**: `005-role-access-isolation`  
**Owner**: API Service authorization domain  
**System of record**: PostgreSQL 15  
**Ephemeral acceleration** (optional): process-local or Redis 7 — never sole copy of role/ownership

## 设计原则

- 用户角色与账户状态以既有 `users` 表为权威；授权**每次**读取当前行，不把
  `auth_sessions.role_snapshot` 当作权限源。
- 资源所有权以本功能 `resource_ownerships` 为权威，直到后续 Key 产品迁入或共用。
- 授权策略矩阵以代码版本 `policy_version` 为权威，不入库可变策略行。
- 审计追加写；禁止凭证、完整代理 Key、完整手机号。
- 时间一律服务端 UTC `timestamptz`。
- 迁移 additive：`0004_role_access_isolation`（接在 `0003_phone_login_session` 之后）。

## Existing Entity：`users`（只读于授权）

| Field | Use in authorization |
|-------|----------------------|
| `id` | 认证后的 actor / owner 比较 |
| `role` | 矩阵输入：`buyer` / `seller` / `both` |
| `status` | 必须 `active` |
| `is_deleted` | 必须 `false` |
| `version` | 可选一致性标记；不单独替代 status |

**Eligible predicate**:

```text
status == active AND is_deleted == false
```

## Existing Entity：`auth_sessions`（仅认证）

授权只依赖会话校验成功得到的 `user_id` / `session_id`。  
`role_snapshot` **不得**参与允许/拒绝判定。

## Entity 1：`resource_ownerships`

表示某资源当前的所有权与可见生命周期（轻量事实，非完整 Key 密钥材料）。

| Field | Type | Null | Constraints / classification |
|-------|------|------|------------------------------|
| `id` | UUID | no | PK |
| `resource_type` | varchar(32) | no | `proxy_key` \| `seller_key` |
| `resource_id` | UUID | no | 业务资源标识 |
| `owner_user_id` | UUID FK users | no | 所有者 |
| `lifecycle_status` | varchar(16) | no | `active` \| `disabled` \| `soft_deleted` |
| `created_at` | timestamptz | no | DB time |
| `updated_at` | timestamptz | no | DB time |
| `version` | integer | no | 乐观并发，默认 1 |
| `created_request_id` | varchar(128) | no | 创建关联 |
| `delete_after` | timestamptz | yes | soft_deleted 后硬删调度可选；null=保留 |

### Constraints and indexes

- UNIQUE (`resource_type`, `resource_id`)。
- CHECK `lifecycle_status` in allowed set。
- CHECK `version >= 1`。
- Index (`owner_user_id`, `resource_type`, `lifecycle_status`) — 自路由排除与列表。
- Index (`resource_type`, `resource_id`) — 点查（与 UNIQUE 重合时可省略第二索引）。
- FK `owner_user_id` → `users.id`（RESTRICT 或 SET NULL 需产品定；推荐 RESTRICT 防悬空所有者）。

### Visibility rules (authorization)

| lifecycle_status | 所有者读改停 | 非所有者 / 未认证 | 路由候选 |
|------------------|--------------|-------------------|----------|
| `active` | 允许（角色矩阵通过时） | 统一 not_found | 可入候选（若非本人买家） |
| `disabled` | 所有者可 `read`/`disable` 视矩阵；`use` 拒绝 | 统一 not_found | **不可**入候选 |
| `soft_deleted` | 对外与不存在相同 | 统一 not_found | **不可**入候选 |

### Lifecycle

```text
(create action success) → active
active → disabled   (disable)
active|disabled → soft_deleted  (产品删除；本功能夹具可模拟)
```

创建时 `owner_user_id` MUST 等于认证用户，禁止客户端指定他人为所有者。

## Entity 2：`authorization_security_events`

追加写的授权安全审计事实（可查询、可保留清理）。

| Field | Type | Null | Constraints / classification |
|-------|------|------|------------------------------|
| `id` | UUID | no | PK |
| `event_type` | varchar(48) | no | 见枚举 |
| `outcome` | varchar(16) | no | `denied` \| `allowed_state_change` \| `error` |
| `reason_code` | varchar(64) | no | 稳定原因，如 `ROLE_DENIED`、`NOT_OWNER`、`SELF_ROUTE_BLOCKED` |
| `action` | varchar(64) | no | 声明动作名 |
| `policy_version` | varchar(32) | no | 如 `authz-matrix-v1` |
| `actor_user_id` | UUID | yes | 已认证时非空 |
| `session_id` | UUID | yes | 关联会话，无 FK 强制（会话可删） |
| `resource_type` | varchar(32) | yes | |
| `resource_ref` | bytea 或 UUID | yes | 资源 ID 明文 UUID 可接受（非密钥）；禁止密钥材料 |
| `request_id` | varchar(128) | no | 关联 |
| `safe_metadata` | jsonb | no | 默认 `{}`；仅低敏字段（候选数量、过滤数量等） |
| `occurred_at` | timestamptz | no | |
| `delete_after` | timestamptz | no | 默认 occurred_at + 90d |

### event_type（V1）

- `authz.role_denied`
- `authz.account_unavailable`
- `authz.ownership_denied`（对外已投影为 not_found，审计可内记 not_owner）
- `authz.self_route_blocked`
- `authz.resource_state_change`
- `authz.unauthenticated`（可选，防刷时需采样/限流）

### Constraints and indexes

- Index (`request_id`)
- Index (`event_type`, `occurred_at`)
- Index (`delete_after`) 供清理
- 禁止 UPDATE/DELETE 业务路径（仅 retention worker 物理删过期行）

## Entity 3：`authorization_audit_outbox`

纯拒绝路径的至少一次投递意图。

| Field | Type | Null | Constraints / classification |
|-------|------|------|------------------------------|
| `id` | UUID | no | PK |
| `payload` | jsonb | no | 与 security event 同构的安全字段 |
| `request_id` | varchar(128) | no | |
| `state` | varchar(16) | no | `pending` \| `published` \| `failed` |
| `attempts` | smallint | no | 默认 0 |
| `available_at` | timestamptz | no | 下次可领取时间 |
| `published_event_id` | UUID | yes | 成功后指向 events.id |
| `created_at` | timestamptz | no | |
| `updated_at` | timestamptz | no | |
| `delete_after` | timestamptz | no | published 后短期保留便于对账 |

### Lifecycle

```text
pending ── worker 成功插入 security_events ──> published
pending ── 瞬时失败（attempts++, backoff）──> pending
pending ── 超过 max attempts ──> failed（告警）
```

**同请求保证**：拒绝响应返回前，MUST 已成功提交至少一行 `pending` outbox
（或同事务直接写入 security_events 并可将 outbox 省略的「同步优化」——若采用同步直写，
仍须满足「无投递证据则不得返回成功拒绝审计语义」：直写失败 → 503）。  
推荐：**优先同事务直写 `authorization_security_events`**；仅当需与只读连接分离时用 outbox。  
V0.1 默认：**拒绝与状态变更均在可写事务中直写 events**；outbox 用于 worker 补写失败重试或
跨连接场景。若直写失败 → 状态变更回滚；纯拒绝 → 503 `SERVICE_UNAVAILABLE`（无法证明审计意图时
不返回业务 403/404）。这比「返回 403 但丢失审计」更符合澄清 Q4 的「禁止静默丢弃」；
与「立即返回拒绝」在 outbox 先落盘成功后返回 403 等价。

**澄清对齐（实现钉死 / analyze I1）**：

1. 开启可写事务  
2. 插入 outbox **或** security_events（至少一种成功提交）  
3. 提交成功后再写 HTTP 403/404  
4. Worker 保证 events 最终可按 `request_id` 查询  

若步骤 2 失败 → **503**，禁止无投递证据的业务拒绝（FR-010a）。

**生命周期钉死**：`proxy_key.revoke` → `lifecycle_status = disabled`。

## Domain value objects（非表）

### AuthorizationAction

`proxy_key.create` | `proxy_key.revoke` | `proxy_key.use` |  
`seller_key.register` | `seller_key.read` | `seller_key.update` | `seller_key.disable` |  
`route_candidate_exclude_self`

### Decision

| Field | Meaning |
|-------|---------|
| `allowed` | bool |
| `http_status` | 401/403/404/503… |
| `code` | 稳定业务码 |
| `reason_code` | 内部/审计原因 |
| `policy_version` | |
| `filtered_candidates` | 仅路由动作 |
| `resource` | 可选可见资源视图 |

### RouteCandidate

`{ resource_id: UUID, owner_user_id: UUID, lifecycle_status: str }`  
排除规则：丢弃 `owner_user_id == buyer_user_id` 或非 `active` 项；**禁止**在过滤后为空时回填本人 Key。

## 不变量

1. 未在矩阵显式允许的 `(role, action)` 一律拒绝。  
2. 客户端 body/query 中的 `user_id` / `role` / `owner_user_id` 不得覆盖会话身份与事实源角色。  
3. 非所有者与不存在对外决策不可区分（404 + 同一 `code`）。  
4. 自路由排除后不得降级选择本人 Key。  
5. 事实源不可用 → 不 allow。  
6. 强制审计范围内的决策在返回成功业务拒绝/变更前具备可恢复投递证据。

## 迁移与备份

- 修订：`0004_role_access_isolation`（名称以实现 head 为准）。  
- 备份：继承 API Service PostgreSQL 实例既有备份/恢复程序；恢复后复核所有权唯一约束与事件追加性。  
- 清理：有界批删 `delete_after < now()` 的 events/outbox；不删 `resource_ownerships` active 行。

## 与后续 Key 功能关系

后续卖家/代理 Key 功能 SHOULD：

- 在创建/转让/删除 Key 时同步维护 `resource_ownerships`（或替换为更富模型并提供兼容读）；  
- 调用同一 `AuthorizationService`；  
- 不得在 Gateway 或前端单独实现角色放行。
