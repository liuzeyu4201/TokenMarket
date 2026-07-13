# Feature Specification: SF14 上游 Key 容量保护

**Feature ID**: `SF14`  
**Short Name**: `upstream-capacity-guard`  
**Created**: 2026-07-13  
**Status**: Draft  
**Source**: 周度 Spec F05/F06、PRD 路由技术约束、Go 并发规范

## 目标与价值

保护每条卖家 Key 不超过火山方舟已知并发/速率上限的 80%，并在上游返回 429 时进入 30 秒请求级冷却。容量通过可过期租约管理，确保成功、失败、超时、取消和进程崩溃后都能恢复。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 不超过单 Key 安全容量 (Priority: P1)

作为卖家，我希望平台限制 Key 的并发占用，避免代理流量触发官方封禁或持续限流。

**Independent Test**: 为测试 Key 配置官方上限，发起超过 80% 阈值的并发请求，验证多余请求不会获得租约。

**Acceptance Scenarios**:

1. **Given** Key 官方并发上限已知，**When** 活跃租约达到其 80%，**Then** SF13 暂时排除该 Key，不再分配新请求。
2. **Given** 任一请求成功、失败、超时或取消，**When** 请求结束，**Then** 对应容量租约只释放一次，Key 有空闲时重新可选。
3. **Given** 有其他 Key 仍有容量，**When** 当前 Key 满载，**Then** 路由可选择其他 Key，不影响其容量计数。

---

### User Story 2 - 响应上游 429 并自动恢复 (Priority: P1)

作为平台，我希望触发 429 的 Key 立即停止接收新请求，并在 30 秒冷却后谨慎恢复。

**Independent Test**: 注入 429，验证 Key 进入冷却、期间不被选择、到期后仅在其他资格满足时恢复。

**Acceptance Scenarios**:

1. **Given** 火山方舟对某 Key 返回 429，**When** 结果被处理，**Then** Key 立即进入 30 秒 cooldown 并从新路由候选中排除。
2. **Given** cooldown 尚未到期，**When** 发生新选择，**Then** 该 Key 不可获得租约。
3. **Given** cooldown 到期且 Key 管理/健康状态正常，**When** 新请求到达，**Then** Key 以正常容量规则恢复，不补发旧请求。

---

### User Story 3 - 从异常退出恢复容量 (Priority: P2)

作为运维人员，我希望网关异常退出不会让容量永久泄漏，也不会在重启后瞬间超卖。

**Acceptance Scenarios**:

1. **Given** 持有租约的网关进程崩溃，**When** 租约超过最大请求期限，**Then** 自动过期并释放容量。
2. **Given** 容量状态存储不可用，**When** 无法原子确认租约，**Then** 失败关闭或使用保守容量，不超出 80% 阈值。

### Edge Cases

- 官方只提供每分钟速率而不提供明确并发上限。
- 80% 计算得到非整数或小于 1。
- 同一请求重复释放、超时释放与正常完成竞争。
- 429 携带 Retry-After 与默认 30 秒不一致。
- 冷却期间卖家暂停或健康检查标记 expired。
- 多网关实例同时获取最后一个容量槽。
- 请求时长超过租约 TTL 但仍在合法流式处理。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 每条 Key MUST 具有版本化容量策略，至少包含官方上限、单位、来源、更新时间和安全利用率 80%。
- **FR-002**: 可分配并发阈值 MUST 为官方并发上限的向下取整 80%，且至少为 1；官方上限未知时采用明确保守默认或保持不可路由。
- **FR-003**: 请求在上游调用前 MUST 原子获取单 Key 容量租约；无法获取时不得使用该 Key。
- **FR-004**: 租约 MUST 关联 request_id、key_id、获取时间和最大期限，不包含原始 Key。
- **FR-005**: 请求成功、失败、超时、取消或 panic 后 MUST 释放租约，释放操作幂等。
- **FR-006**: 进程崩溃遗留租约 MUST 在有界 TTL 后自动过期；长请求必须安全续租且不能无限延期。
- **FR-007**: 上游 429 MUST 立即创建该 Key 的 30 秒请求级 cooldown；若可靠 Retry-After 更长，则采用更长值并记录来源。
- **FR-008**: cooldown 期间 Key MUST 不可获得新租约；到期不会覆盖 paused、revoked、down、expired 或 invalid 状态。
- **FR-009**: V0.1 MUST NOT 自动重试触发 429 的 Chat Completion；客户端请求按 SF12/SF15 返回既定错误。
- **FR-010**: 容量存储不可用或状态不可信时 MUST 失败关闭或使用经证明不超卖的保守策略。
- **FR-011**: 容量和 cooldown 变化 MUST 在 1 秒内反映给 SF13。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: SF13 查询容量资格，SF12/SF15 获取/释放租约并报告 429；接口须定义原子性、TTL、幂等释放和错误。
- **ER-002 — Security & Privacy**: 容量管理只使用内部 key_id；配置与管理入口需授权，日志不得包含凭证。
- **ER-003 — Data Integrity**: Redis 可保存租约/cooldown 等临时事实，但持久容量策略有明确所有者；原子操作防止跨实例超卖。
- **ER-004 — Performance & Capacity**: 租约获取/释放 P95 小于 5 毫秒；在 >100 QPS 下仍不超过每 Key 阈值。
- **ER-005 — Reliability**: TTL、续租、优雅关闭、panic/取消释放、存储故障降级和重启恢复必须可测试。
- **ER-006 — Observability**: 按 Key 脱敏 ID 暴露活跃租约、阈值、拒绝数、cooldown、429、租约过期和泄漏修复计数。
- **ER-007 — Accessibility**: 内部能力无界面；容量不足映射为稳定公开错误和 request_id，不暴露卖家容量细节。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** 请求获取租约后进程崩溃，**When** TTL 到期，**Then** 容量自动恢复且产生租约过期信号。
2. **Given** 正常完成与超时处理同时释放，**When** 两者竞争，**Then** 只减少一次活跃计数，不出现负值。
3. **Given** 容量存储分区，**When** 无法原子获取租约，**Then** 新请求不超卖；恢复后从现存租约重建一致计数。

### Key Entities

- **Capacity Policy**: key_id、官方限制、单位、安全比例、有效阈值、来源和版本。
- **Capacity Lease**: request_id、key_id、状态、获取/续租/过期时间；临时且幂等释放。
- **Rate-Limit Cooldown**: key_id、开始/结束、触发状态、Retry-After 来源和版本。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 10 万次并发租约竞争中，任何时刻活跃数都不超过配置阈值。
- **SC-002**: 成功、失败、超时、取消和 panic 测试结束后活跃租约全部归零，无负计数。
- **SC-003**: 429 后 1 秒内该 Key 新租约数为 0，30 秒或更长 Retry-After 到期后可按资格恢复。
- **SC-004**: 租约获取/释放 P95 小于 5 毫秒，>100 QPS 下无容量超卖。
- **SC-005**: 进程崩溃后所有遗留租约在定义 TTL 内释放，恢复无需人工修改计数。

## Scope

### In Scope

- 单 Key 并发阈值、容量租约、429 请求级冷却、恢复和多实例原子控制。

### Out of Scope

- 买家速率限制、计费额度、智能路由权重、健康检查 30 分钟冷却和自动上游重试。

## Test Requirements

- 原子租约与幂等释放单元测试。
- 竞态测试覆盖最后槽位、重复释放、续租和 TTL 过期。
- 故障注入覆盖进程崩溃、存储分区、429 与状态竞争。
- Benchmark/负载测试验证 5 毫秒和 >100 QPS 目标。
- 容量领域至少 80% 行覆盖，泄漏、超卖和失败关闭分支直接覆盖。

## Assumptions

- 依赖 SF13 候选池；SF12/SF15 管理请求生命周期。
- 官方限制值由配置或验证结果提供并标注来源；未知时不猜测高容量。
- SF16 的健康检查 429 冷却 30 分钟与本功能请求级 30 秒 cooldown 分离。

## Traceability

- 周度 Spec：F05 429、F06 单 Key 80% 限速边界。
- PRD：4.3.1 技术约束中的 80% 上限和级联故障风险。
- 规范：`2-Go代理网关开发规范.md` 第 3.2、6、7.3 节。
- 宪章：原则 I、III、V、VI。
