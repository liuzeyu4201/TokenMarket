# Feature Specification: SF09 卖家 API Key 生命周期管理

**Feature ID**: `SF09`  
**Short Name**: `seller-key-lifecycle`  
**Created**: 2026-07-13  
**Status**: Draft  
**Source**: 周度 Spec F03、PRD Key 管理、数据库与授权规范

## 目标与价值

允许卖家安全地暂停、恢复和撤销自己接入的 Key，并把人工管理状态与自动健康状态分离。暂停或撤销只影响新请求，已经进入上游的请求允许按既定超时完成；撤销会使凭证不可恢复。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 暂停和恢复 Key (Priority: P1)

作为卖家，我希望随时暂停 Key 避免接收新流量，并在重新验证后恢复使用。

**Independent Test**: 对 active Key 执行暂停，验证候选池立即排除；随后恢复并验证通过后重新加入。

**Acceptance Scenarios**:

1. **Given** 卖家拥有 active Key，**When** 暂停，**Then** administrative_state 变为 paused，并在 1 秒内停止接收新请求。
2. **Given** Key 被暂停且 SF06 重新验证为有效、正额度，**When** 卖家恢复，**Then** administrative_state 变为 active，并由健康与容量规则决定是否回池。
3. **Given** 恢复验证失败或额度为零，**When** 请求恢复，**Then** Key 保持 paused，并返回可操作的安全原因。
4. **Given** 相同状态操作被重复提交，**When** 使用相同幂等键，**Then** 返回首次结果且不重复写审计。

---

### User Story 2 - 不可逆撤销 Key (Priority: P1)

作为卖家，我希望撤销不再使用的 Key，使平台无法再用它调用上游。

**Independent Test**: 撤销一条无进行中请求的 Key，验证新路由立即排除、密文无法解密、审计元数据仍可追踪。

**Acceptance Scenarios**:

1. **Given** 卖家确认撤销自己的 Key，**When** 操作成功，**Then** administrative_state 变为 revoked，新请求立即不可选择，敏感密文被加密擦除或不可恢复删除。
2. **Given** Key 已 revoked，**When** 请求恢复或再次撤销，**Then** 恢复被拒绝，重复撤销幂等返回已撤销状态。
3. **Given** Key 存在进行中请求，**When** 卖家暂停或撤销，**Then** 新请求立即停止，进行中请求允许在原超时内完成且不迁移到其他 Key。

---

### User Story 3 - 拒绝越权和竞争状态变更 (Priority: P1)

作为 Key 所有者，我希望其他用户不能猜测 ID 后修改我的 Key，两个并发操作也不能产生非法状态。

**Acceptance Scenarios**:

1. **Given** Key 属于其他卖家，**When** 当前用户请求暂停、恢复或撤销，**Then** 操作被拒绝且不泄露 Key 详情。
2. **Given** 暂停与撤销并发，**When** 竞争提交，**Then** 最终状态只能是 revoked，且审计顺序可解释。

### Edge Cases

- Key 已因健康检查变为 down、expired 或 rate_limited 时手工暂停。
- 恢复验证成功但路由池刷新失败。
- 撤销时密文清除成功但审计提交失败，或相反。
- 客户端收到超时但服务器已完成状态变更。
- 乐观锁版本过期。
- 状态更新与路由选择在同一毫秒竞争。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 只有 Key 所有者且具有卖家角色的 active 会话可以发起暂停、恢复或撤销。
- **FR-002**: 系统 MUST 分离 administrative_state（active、paused、revoked）与 health_state（healthy、down、rate_limited、expired、invalid、unknown）。
- **FR-003**: 路由候选 MUST 同时要求 administrative_state=active 和 health_state=healthy；人工暂停不得被自动健康恢复覆盖。
- **FR-004**: active → paused、paused → active、active/paused → revoked 为允许转换；revoked 为终态，其他转换返回状态冲突。
- **FR-005**: 暂停或撤销 MUST 在 1 秒内对所有新路由选择生效。
- **FR-006**: 恢复 MUST 调用 SF06 重新验证；只有有效且正额度结果才能切换为 active。
- **FR-007**: 暂停和撤销 MUST NOT 强制中断已经进入上游的请求；这些请求仍受原有超时和计量规则约束。
- **FR-008**: 撤销 MUST 使原始凭证不可再解密，并保留不含秘密的所有权、状态和审计元数据。
- **FR-009**: 所有状态变更 MUST 接受幂等键并使用版本或等价并发控制；相同操作重放不产生重复副作用。
- **FR-010**: 每次成功或拒绝的敏感状态操作 MUST 记录操作者、Key 脱敏标识、前后状态、原因、版本、时间和 request_id。
- **FR-011**: 路由缓存更新失败时，持久状态仍为事实源；系统 MUST 失败关闭，避免继续选择已暂停/撤销 Key。
- **FR-012**: 卖家查询状态时只能看到脱敏 Key、管理状态、健康状态、额度和安全错误摘要。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: 生命周期接口与状态机须版本化；错误区分 unauthorized、forbidden、not_found、invalid_transition、validation_failed、conflict 和 cleanup_failed。
- **ER-002 — Security & Privacy**: 服务端所有权检查、敏感操作审计、幂等/重放防护和撤销后的密码学删除为强制要求。
- **ER-003 — Data Integrity**: PostgreSQL 是状态事实源；状态更新、审计和密文擦除须形成可恢复的一致过程，版本冲突不得覆盖更新。
- **ER-004 — Performance & Capacity**: 暂停/撤销的持久状态和路由失效 P95 小于 1 秒；恢复受 SF06 的 3 秒验证截止约束。
- **ER-005 — Reliability**: 缓存失效失败时不得继续路由；撤销清理应可重试且不会重新暴露已擦除秘密。
- **ER-006 — Observability**: 暴露按前后状态、失败原因和传播延迟聚合的指标，审计和日志不含凭证。
- **ER-007 — Accessibility**: V0.1 无前端；状态与错误必须具有稳定机器代码和可操作说明。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** 持久状态已暂停但缓存刷新失败，**When** 新请求选择候选，**Then** 通过版本/事实校验拒绝该 Key，并触发缓存失效告警。
2. **Given** 两个并发状态操作使用旧版本，**When** 提交，**Then** 最多一个成功，另一个返回冲突并可读取新状态重试。
3. **Given** 撤销在敏感密文清理阶段中断，**When** 恢复任务重试，**Then** Key 始终保持不可路由，直到密文确认不可恢复并完成审计。

### Key Entities

- **Seller Key Lifecycle**: administrative_state、health_state、版本、状态原因和时间；持久事实由 Key 所有域维护。
- **Key State Transition**: 幂等键、操作者、前后状态、触发原因、版本和 request_id；不可修改审计事实。
- **Credential Destruction Record**: 密文/密钥版本清除结果、时间和执行者，不包含秘密材料。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 暂停或撤销后 1 秒内，新路由选择该 Key 的次数为 0。
- **SC-002**: 100% 恢复操作在重新验证成功前保持不可路由。
- **SC-003**: 所有状态机非法转换和越权操作拒绝率为 100%。
- **SC-004**: 100 个并发暂停/恢复/撤销竞争后，最终状态满足状态机且审计可重放解释。
- **SC-005**: 撤销后的凭证恢复测试成功次数为 0，同时 100% 操作保留脱敏审计元数据。

## Scope

### In Scope

- 单条卖家 Key 的暂停、恢复、撤销、状态查询、缓存传播和审计。

### Out of Scope

- 周期健康检查、批量操作、自动余额过期判断、挂售配置和前端。

## Test Requirements

- 状态机表驱动测试覆盖全部允许/拒绝转换。
- 集成测试覆盖事务、乐观锁、路由缓存失效和迁移回退。
- 安全测试覆盖 IDOR、审计、重放和撤销后不可恢复。
- 并发测试覆盖暂停/恢复/撤销竞争与路由选择竞争。
- Key 生命周期领域至少 80% 行覆盖，授权、并发和擦除分支直接覆盖。

## Assumptions

- 依赖 SF08 的加密 Key 记录、SF05 的授权、SF06 的恢复验证。
- SF16 只更新 health_state，不覆盖 administrative_state。
- 敏感密文的删除方式由计划确定，但结果必须满足不可恢复。

## Traceability

- 周度 Spec：F03-A4。
- PRD：4.1.1 AC-1.1.5、AC-1.1.6；4.1.2 AC-1.2.6 的进行中请求规则。
- 规范：`3-Python后端与数据库设计规范.md` 第 4.2.2、4.3、4.5、6、7 节。
- 宪章：原则 II、III、V、VI。
