# Phase 0 Research：角色授权与自买自卖隔离

**Feature**: `005-role-access-isolation`  
**Date**: 2026-08-01  
**Status**: Complete — 所有研究问题均已解决（含 2026-08-01 analyze 收口 D14）

## Decision 1：边界保持在 API Service 授权域，不新建服务

**Decision**: 权限矩阵、资源所有权校验、自买自卖排除、授权审计与相关指标由
`services/api-service/` 的 `authorization` 领域拥有。PostgreSQL 仅由 API Service 访问。
Frontend 无交付面。Proxy Gateway、Billing、Admin 本功能不实现代理热路径消费；后续
路由/代理功能通过版本化契约与可移植纯函数/端口消费「排除卖家 ID」与决策语义。

**Rationale**: 用户角色与账户状态已由 API Service `users` 域拥有；会话认证由
`authentication` 域拥有。授权紧邻用户事实，避免新微服务与跨库访问，符合宪章 I。

**Alternatives considered**:

- 新建 authorization-service：V0.1 动作面与流量不足以承担独立服务/ADR 成本。
- 在 Gateway 复制 RBAC：会形成双源策略与 Python 领域漂移。
- 仅依赖会话 `role_snapshot`：已被规格澄清否决（须读事实源当前角色）。

## Decision 2：策略以版本化代码矩阵为权威，非可热改 DB 策略引擎

**Decision**: V0.1 默认拒绝矩阵以领域代码定义（`policy_version` 字符串，如
`authz-matrix-v1`），动作与角色允许关系表驱动、可单测。变更通过评审发布，不提供
运行时管理员改矩阵 UI/API。审计事件记录当时 `policy_version`。

**Rationale**: 规格要求可 100% 表驱动测试；静态矩阵可证明、可 diff、无策略注入面。
完整策略引擎属于过早抽象。

**Alternatives considered**:

- DB 可配置策略：增加管理面、缓存一致性与安全面，超出 V0.1。
- 外部 OPA/Casbin：新依赖与运维路径，当前动作集过小。

## Decision 3：身份 = 会话用户 ID；角色/状态 = 每次读 `users` 事实源

**Decision**: 受保护请求先完成 SF04 会话认证，仅提取 `user_id`（及 `session_id` 用于
审计关联）。授权阶段用短查询读取 `users.role`、`users.status`、`users.is_deleted`（及
`version` 作为可选乐观读一致性标记），**忽略** `auth_sessions.role_snapshot` 作权限依据。
非 `active` 或 `is_deleted=true` 或会话已撤销 → 拒绝全部受保护动作。

**Rationale**: 直接落实澄清 Q1 与 FR-005a/006/009；与 SF04 data-model 中
「后续授权仍检查当前账户」一致。

**Alternatives considered**:

- 信任会话角色快照：变更延迟不可控，违反 1 秒生效。
- 仅在 role 变更时广播失效：仍需可靠失效通道；读当前行更简单且可测。

## Decision 4：V0.1 直读事实源；加速层范围外

**Decision**: **V0.1 不实现**授权加速层（spec 范围外）。一律直读 PostgreSQL 角色/
所有权/状态，以满足 SC-004a 与 fail-closed。若未来引入加速副本：

- 仅缓存 `(user_id → role, status, is_deleted, version)` 与
  `(resource_type, resource_id → owner_user_id, status)`；
- 失效窗口 **≤1s**（SC-003）；故障 **回源** 或拒绝，禁止 fail-open；
- 命中路径另验收 SC-004b（P95≤10ms）。

**Rationale**: ER-004/005 分层；简化首版交付；宪章 III（Redis 非唯一事实）。

**Alternatives considered**:

- 首版强依赖 Redis 加速：增加故障面，非必需。
- 进程内无界缓存：可后续增量，不在本计划任务内。

## Decision 5：所有权事实用轻量 `resource_ownerships` 表，完整 Key 产品延后

**Decision**: 新增 API Service 表 `resource_ownerships`，记录
`resource_type ∈ {proxy_key, seller_key}`、`resource_id`、`owner_user_id`、
`lifecycle_status ∈ {active, disabled, soft_deleted}` 等。本功能提供仓储与写接口
（领域 API + **仅 test/local 的夹具 HTTP** 或测试直接仓储写入）以支撑矩阵与所有权/
自路由测试。完整卖家 Key / 代理 Key 产品 REST 与密钥材料加密存储属于后续功能；
后续功能 MUST 写入或迁移到同一所有权事实（或兼容视图），不得旁路。

**Rationale**: 澄清 Q3 要求可测声明动作族而不强塞完整 Key 产品 API。

**Alternatives considered**:

- 纯内存桩：集成/迁移/并发所有权变更难验收。
- 直接实现完整 Key CRUD+加密：范围膨胀到后续 SF。

## Decision 6：跨用户资源统一 404；角色不足 403；未认证 401

**Decision**:

| 条件 | HTTP | 稳定业务码 |
|------|------|------------|
| 未认证 / 会话无效 | 401 | `UNAUTHENTICATED` |
| 已认证，角色不允许该动作 | 403 | `FORBIDDEN_ROLE` |
| 账户 suspended / soft / 非 active | 403 | `ACCOUNT_UNAVAILABLE`（文案中性，不区分 suspended vs deleted 细节） |
| 按 ID 资源不存在、soft_deleted 不可见、非所有者 | 404 | `RESOURCE_NOT_FOUND`（三者不可区分） |
| 自路由后无可用候选 | 404 或 409（契约钉死一种） | `NO_ROUTE_CANDIDATE` |
| 事实源不可达 | 503 | `SERVICE_UNAVAILABLE` |

**自路由无候选**：采用 **404 + `NO_ROUTE_CANDIDATE`**（表示对调用方「无可用资源」，
不暗示本人 Key 存在）。矩阵单元测试直接断言排除集合，不依赖 HTTP。

**Rationale**: 澄清 Q2；与 FR-007a、ER-001 一致。

**Alternatives considered**:

- 非所有者 403：可枚举存在性。
- 自路由无候选 403：易与角色拒绝混淆。

## Decision 7：授权决策单一入口 + 表驱动矩阵

**Decision**: 领域服务 `AuthorizationService.authorize(decision_request) → Decision`：

输入：`user_id`（来自会话）、`action`、`resource_type`（可空）、`resource_id`（可空）、
`request_id`、可选候选集（路由排除）。

处理顺序（固定）：

1. 加载用户事实；失败关闭  
2. 账户可登录谓词（active ∧ ¬deleted）  
3. 矩阵：`(role, action)` 是否允许  
4. 若动作绑定资源：加载所有权；非本人 / 不可见 → 统一 not_found  
5. 若动作为 `route_candidate_exclude_self`：过滤 `owner_user_id == buyer_user_id`  
6. 记录指标；按策略写审计  

声明动作（FR-001a）：

| Action | 资源类型 | buyer | seller | both |
|--------|----------|-------|--------|------|
| `proxy_key.create` | proxy_key（创建时无既有 ID） | ✓ | ✗ | ✓ |
| `proxy_key.revoke` | proxy_key | ✓ | ✗ | ✓ |
| `proxy_key.use` | proxy_key | ✓ | ✗ | ✓ |
| `seller_key.register` | seller_key | ✗ | ✓ | ✓ |
| `seller_key.read` | seller_key | ✗ | ✓ | ✓ |
| `seller_key.update` | seller_key | ✗ | ✓ | ✓ |
| `seller_key.disable` | seller_key | ✗ | ✓ | ✓ |
| `route_candidate_exclude_self` | n/a（操作候选集） | ✓* | ✗ | ✓ |

\* buyer 可调用路由排除（作为买家流量侧）；seller-only 无买家路由语义 → 拒绝。

创建类动作在写入时设置 `owner_user_id = 当前用户`；读改停必须所有权匹配。

**Rationale**: 单一入口避免路由层散落 if；表驱动支撑 SC-001。

## Decision 8：审计模型 — 强制路径与 outbox 至少一次

**Decision**:

- 表 `authorization_security_events`：追加写、脱敏、含 `policy_version`、
  `decision`、`reason_code`、`action`、`actor_user_id`、资源脱敏引用、
  `request_id`、`occurred_at`、`delete_after`。
- 表 `authorization_audit_outbox`：纯拒绝路径在**返回业务 403/404 之前**必须先成功
  提交 event 或 pending outbox（与请求标识关联）；后台/同进程 worker 可将 outbox
  刷入 `authorization_security_events`（至少一次）。**若意图无法落盘 → 503**，禁止
  「无证据的业务拒绝」（分析收口 I1 / FR-010a）。
- 敏感状态变更（夹具创建/停用资源、未来 Key 写路径）：事件与业务变更**同一事务**。
- 高频允许：`proxy_key.use` 允许、路由排除成功后的继续 → **不写**逐条授权审计，
  只加指标（澄清 Q5）。
- V0.1 推荐：可写事务内直写 `authorization_security_events`；outbox 用于补写/跨连接。

保留：授权安全事件默认 `delete_after = occurred_at + 90 days`（可配置，须 ≥ 平台
合规下限）；清理可复用认证 cleanup 模式的有界批处理命令或扩展现有 maintenance。

**Rationale**: 澄清 Q4/Q5 与 analyze I1：禁止静默丢审计；「立即拒绝」以落盘成功为前提。

**Alternatives considered**:

- 先返回 403 再尽力写审计：可静默丢失，违反 FR-010a。
- 纯内存/日志审计：不满足按 request_id 查询与至少一次。

## Decision 9：夹具 HTTP 仅 test/local，生产 fail-closed 关闭

**Decision**: 为集成验收提供受开关保护的夹具路由（示例前缀
`/api/v1/authorization/fixtures/...` 或等价），用于：

- 以当前会话身份尝试声明动作（create/read/disable stub 资源、use、route exclude）；
- 管理测试资源所有权行（仅非 production）。

开关：`AUTHORIZATION_FIXTURES_ENABLED` 默认 false；仅 `APP_ENV in {local,test}` 且
显式 true 时可挂载。production/staging 误开 → 启动或 readiness fail-closed。

完整 OpenAPI 描述夹具与决策错误码，便于契约测试；实现提升到
`shared/contracts/role-access-isolation/v1/`。

**Rationale**: 无完整 Key API 时仍可做 HTTP 级矩阵与 IDOR 负向测试。

## Decision 10：Gateway / 计费暂不接线；导出可复用决策语义

**Decision**: 本功能不修改 proxy-gateway 热路径。导出：

1. 版本化业务码与决策原因枚举（契约）；  
2. 纯函数 `exclude_self_owned_seller_keys(buyer_user_id, candidates)`；  
3. 领域 `authorize` 语义说明（后续可由 Gateway 经内部 RPC/共享库消费——若跨语言则
   仅契约 + 侧车/HTTP evaluate，须另开 ADR；V0.1 不强制）。

**Rationale**: 无代理 Key 生产流量时过早改 Gateway 无验收对象。

## Decision 11：测试策略

**Decision**:

- 单元：完整角色×动作表、所有权、自排除、账户状态、客户端伪造 user_id 忽略。  
- 集成：真实 PostgreSQL；会话 + 授权夹具；并发角色变更与读一致性；outbox 刷写；
  **会话撤销后 evaluate → 401**（SC-006）；审计意图落盘失败 → 503。  
- 负向：IDOR 统一 404、未认证/撤销 401、角色 403。**不**测批量 API（范围外）。  
- 性能：直读 P95（SC-004a）env 门控微基准；加速路径仅当实现后测（默认跳过）。  
- 覆盖：`authorization` 域与路由 ≥80% 行；拒绝/自买自卖/失败关闭/审计顺序分支直接断言。

**Rationale**: 宪章 V 与规格 Test Requirements + analyze C1/I1/I2/U1。

## Decision 12：迁移与回滚

**Decision**: Alembic additive 修订 `0004_role_access_isolation`（名称以实现时 head
为准）：创建 `resource_ownerships`、`authorization_security_events`、
`authorization_audit_outbox`（及必要索引）。不编辑已应用 0002/0003。常规回滚停用
夹具与新入口、保留表与审计；破坏性 downgrade 仅隔离环境 + 显式授权。

**Rationale**: 宪章 III expand/migrate/contract。

## Decision 13：文档语言

**Decision**: Spec/Plan/Research/Data-model/Quickstart/Checklist 以简体中文为主；
OpenAPI 字段名、业务码、枚举、路径保持英文标识。

**Rationale**: 宪章 Principle VIII / 文档语言门禁。

## Decision 14：规格 analyze 收口（2026-08-01）

**Decision**:

1. **I1**：拒绝响应前必须成功提交审计事件或 pending 意图；否则 **503**（非裸 403/404）。  
2. **I2**：性能分层 SC-004a/b/c；V0.1 **不实现**加速层，验收 a+c。  
3. **U1**：无批量授权 API（FR-011 范围外）。  
4. **C1**：会话撤销/过期/缺失 → `UNAUTHENTICATED` 401，不进入矩阵允许。  
5. **revoke**：`proxy_key.revoke` → `lifecycle_status=disabled`。

**Rationale**: 消除 plan/tasks 与澄清措辞冲突，保证可实施唯一语义。

**Alternatives considered**: 先 403 再尽力审计 — 已否决。

## Resolved Technical Context Notes

| 原疑点 | 结论 |
|--------|------|
| 授权放哪 | API Service authorization 域 |
| 是否 JWT/网关 RBAC | 否；会话 + 事实源 |
| 完整 Key API | 否；所有权表 + 夹具 |
| 审计同步性 | 变更同事务；拒绝**先落盘意图**再 403/404，失败 503 |
| 缓存/加速 | V0.1 不实现；未来可选且 fail-closed |
| 批量 API | 范围外 |
| 会话撤销 | 401，SC-006 |
| 前端 | 无 |
