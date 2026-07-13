# Feature Specification: SF13 可用 Key 池与轮询选择

**Feature ID**: `SF13`  
**Short Name**: `round-robin-key-routing`  
**Created**: 2026-07-13  
**Status**: Draft  
**Source**: 周度 Spec F06/F09、路线图基础轮询、Go KeyPool/路由规范

## 目标与价值

维护火山方舟可用卖家 Key 的可重建候选池，并在每次买家请求时执行公平、并发安全的 Round-Robin 选择。V0.1 不采用价格、延迟、卖家等级或会话亲和性加权。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 公平轮询可用 Key (Priority: P1)

作为平台，我希望请求在合格卖家 Key 之间均匀分布，避免单条 Key 被持续占用。

**Independent Test**: 固定两个相同资格候选，连续选择 10 次，验证每条恰好 5 次且顺序确定。

**Acceptance Scenarios**:

1. **Given** 两条合格 Key 且候选集合稳定，**When** 连续选择 10 次，**Then** 每条被选 5 次。
2. **Given** 三条合格 Key 并发接收大量选择，**When** 统计完整轮次，**Then** 任意两条选择次数差不超过 1。
3. **Given** 候选池顺序从事实源刷新，**When** 新 Key 加入，**Then** 轮询继续有效且不会长期饿死任一 Key。

---

### User Story 2 - 只选择符合约束的 Key (Priority: P1)

作为买家和卖家，我希望路由排除暂停、撤销、过期、不健康、限流、满载或属于买家自己的 Key。

**Independent Test**: 构造每种不可用状态和本人所有权候选，验证选择结果不包含任何被排除项。

**Acceptance Scenarios**:

1. **Given** 候选混合多种状态，**When** 过滤，**Then** 只保留 platform=volcano、管理 active、健康 healthy、额度正数且有容量的 Key。
2. **Given** 当前 buyer 同时拥有卖家 Key，**When** 过滤，**Then** 其全部 Key 被排除。
3. **Given** 没有合格候选，**When** 选择，**Then** 返回 no_available_key，由代理映射为 503，不发起上游请求。

---

### User Story 3 - 在多实例与状态变化下保持正确 (Priority: P1)

作为运维人员，我希望多个网关实例并发路由时仍保持近似公平，并在 Key 状态变化后快速停止选择。

**Acceptance Scenarios**:

1. **Given** 多个网关实例共享路由状态，**When** 并发选择，**Then** 轮询计数无数据竞争且分布满足公平阈值。
2. **Given** Key 被暂停、撤销或标记不健康，**When** 状态传播完成，**Then** 后续选择不再返回该 Key。

### Edge Cases

- 候选集在一次选择前后发生增删或重新排序。
- Redis 缓存丢失、返回旧版本或不可用。
- 多实例同时读取并推进同一轮询位置。
- Key 刚被选中就暂停、撤销或容量耗尽。
- 所有合格 Key 都属于当前 buyer。
- 重复 Key ID、额度单位不一致或状态数据损坏。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 候选 MUST 满足 platform=volcano、administrative_state=active、health_state=healthy、remaining_quota>0、未软删除且有可分配容量。
- **FR-002**: 候选 MUST 排除 seller_id 等于当前 authenticated buyer_id 的全部 Key。
- **FR-003**: V0.1 选择策略 MUST 为等权 Round-Robin；不得引入价格、延迟、成功率、等级或会话亲和权重。
- **FR-004**: 候选集合稳定时，每完成一轮每条 Key MUST 恰好被选择一次。
- **FR-005**: 多实例并发推进轮询位置 MUST 使用原子、并发安全机制，不得产生数据竞争或长期偏斜。
- **FR-006**: Redis MAY 保存候选快照和轮询位置，但 PostgreSQL 仍是 Key 状态与所有权事实源，缓存丢失后必须可重建。
- **FR-007**: 候选快照 MUST 带版本或更新时间，状态更新后在 1 秒内失效不可用 Key。
- **FR-008**: 选择返回 MUST 只包含内部 key_id 和执行上游所需的受控引用，不暴露原始 Key 给调用方或日志。
- **FR-009**: 无可用 Key MUST 返回稳定领域错误，不 panic、不返回空对象、不自动选择本人或不健康 Key。
- **FR-010**: 选择后、解密/转发前 MUST 再次确认管理状态、所有权和容量租约，关闭检查与使用之间的竞争窗口。
- **FR-011**: 每次选择 MUST 关联 request_id，并产生不含凭证的候选数量、排除原因和选中脱敏 ID 遥测。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: 路由输入为 buyer_id/platform/request_id，输出为内部 Key 引用或 no_available_key；契约不得包含解密后的凭证。
- **ER-002 — Security & Privacy**: 自买自卖排除、服务端身份、内部管理接口认证、Key 脱敏和默认拒绝为强制要求。
- **ER-003 — Data Integrity**: 持久状态与缓存版本一致；轮询位置可丢失重建，但不能成为所有权、健康或额度事实。
- **ER-004 — Performance & Capacity**: 路由选择 P95 小于 10 毫秒，缓存命中 P95 小于 5 毫秒，并支持 >100 QPS。
- **ER-005 — Reliability**: 缓存不可用时采用有界事实源降级或返回 503；不得使用无限期旧候选继续路由。
- **ER-006 — Observability**: 暴露选择耗时、候选数、排除原因、每 Key 选择计数、公平偏差、缓存年龄和无候选计数。
- **ER-007 — Accessibility**: 内部能力无界面；公开代理只接收稳定 no_available_key 错误，不泄露卖家池细节。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** Redis 丢失全部轮询状态，**When** 系统恢复，**Then** 从事实源重建候选并从安全位置重新轮询，不选择不可用 Key。
2. **Given** Key 在选择后被撤销，**When** 转发前二次校验，**Then** 放弃该 Key 并返回/重新选择的行为按不重放约束执行，不使用已撤销凭证。
3. **Given** 多实例竞争导致原子状态更新暂时失败，**When** 选择重试，**Then** 在有界时间内完成或返回 503，不阻塞请求到超时。

### Key Entities

- **Key Pool Snapshot**: 平台、版本、生成时间和脱敏候选元数据；可重建、非事实源。
- **Route Candidate**: key_id、seller_id、平台、管理/健康状态、精确额度和容量可用性。
- **Round-Robin Cursor**: 平台/候选版本对应的原子位置；允许丢失但不可破坏候选资格。
- **Route Decision**: request_id、候选版本、选中 key_id 和耗时；不包含原始凭证。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 两条可用 Key 连续 10 次选择各命中 5 次。
- **SC-002**: 稳定候选池 10 万次并发选择中，任意两条合格 Key 的选择差异不超过 1%。
- **SC-003**: 暂停、撤销、不健康、零额度、满载和本人 Key 被选中次数均为 0。
- **SC-004**: 路由 P95 小于 10 毫秒，缓存命中 P95 小于 5 毫秒，持续吞吐超过 100 QPS。
- **SC-005**: 无候选和缓存故障场景 100% 返回确定错误且无 panic。

## Scope

### In Scope

- 火山方舟候选池、资格过滤、等权轮询、多实例并发、缓存重建和路由决策。

### Out of Scope

- 智能加权、价格/延迟策略、会话亲和、上游转发、健康探测和容量阈值计算。

## Test Requirements

- 确定性单元测试覆盖资格过滤和轮询序列。
- 并发/竞态测试覆盖多实例游标和状态变化。
- 集成测试覆盖数据库事实、缓存重建、版本失效和管理状态传播。
- Benchmark 与负载测试记录 P95、QPS 和公平偏差。
- 路由领域至少 80% 行覆盖，自路由、无候选、缓存失败和竞争分支直接覆盖。

## Assumptions

- 依赖 SF05 自路由规则、SF08/SF09 Key 所有权与管理状态。
- SF16 更新健康状态，SF14 提供容量可用性和租约。
- 代理 Key 不绑定卖家 Key；F09 固定绑定原要求已被父索引决策替代。

## Traceability

- 周度 Spec：F06-A1 至 F06-A4；F09-A2/A3 的映射由动态路由解释。
- 路线图：V0.1 基础 Round-Robin。
- 规范：`2-Go代理网关开发规范.md` 第 3.2.1、3.2.2、6.4、7.3 节。
- 宪章：原则 I、II、III、V、VI。
