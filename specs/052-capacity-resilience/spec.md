# Feature Specification: 容量、压力、耐久与韧性验收

**Feature Branch**: `052-capacity-resilience`

**Created**: 2026-08-31

**Status**: Implemented

**Input**: User description: "V0.2 500 RPS、长连接、压力、耐久与韧性验收"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF33-容量压力耐久与韧性验收.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 容量用什么 upstream？ → A: 可控 mock；真实厂商仅预算内冒烟，未授权则列为发布阻塞项。
- Q: 负载模型？ → A: 三协议、不同尺寸、工具调用、流式、失败、限流、长尾。
- Q: 租户？ → A: 500 独立买家/Project/Key，种子版本化，验证隔离。
- Q: 备份？ → A: PostgreSQL SoR，RPO ≤5 分钟，RTO ≤30 分钟；Redis 不可充当账本。
- Q: 三次门槛？ → A: 同一候选版本连续 3 次达标才算发布证据。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 稳态与突发吞吐 (Priority: P1)

500 名买家在 mock 上跑 baseline、500 RPS 30 分钟、1000 RPS 5 分钟；成功率与平台新增延迟达标，突发后恢复。

**Independent Test**: 同一引擎按 profile 打真实透传路径；统计成功率与平台 p95。

**Acceptance Scenarios**:

1. **Given** 500 RPS 稳态 profile，**When** 跑完窗口，**Then** 成功率 ≥99.9% 且平台新增 p95 ≤100 ms。
2. **Given** 1000 RPS 突发 5 分钟，**When** 结束，**Then** 无崩溃、无失控积压，降载后恢复基线。
3. **Given** 500 租户种子，**When** 并发请求，**Then** 无跨租户泄漏。

---

### User Story 2 - 长连接耐久 (Priority: P1)

500 条 SSE/WebSocket 持续 2 小时；异常断开 ≤0.5%，内存无无界增长。

**Independent Test**: 经内核打开 500 条流，统计断开率与堆差值。

**Acceptance Scenarios**:

1. **Given** 500 条 SSE，**When** 窗口结束，**Then** 异常断开率 ≤0.5%。
2. **Given** 同一窗口，**When** 对比起止堆，**Then** 无持续无界增长。

---

### User Story 3 - 故障注入与备份恢复 (Priority: P1)

注入实例终止、Redis 重启、数据库短断、事件积压、upstream 故障；恢复后无越权、重复扣费、丢事件；备份满足 RPO/RTO。

**Independent Test**: 注入后核对账本与隔离；备份/恢复计时。

**Acceptance Scenarios**:

1. **Given** upstream/协调故障，**When** 恢复，**Then** 无重复扣费、无丢失可结算事件。
2. **Given** 压测结束，**When** 核对，**Then** 所有 reservation 已终结，账本与请求统计一致。
3. **Given** 演练备份，**When** 恢复到空实例，**Then** RPO ≤5 分钟且 RTO ≤30 分钟。

---

### Edge Cases

- mock 证明平台容量，不代表厂商 SLA。
- 专享故障不得回退共享池。
- 未授权真实厂商冒烟不得用不可控 upstream 顶替容量门禁。

## Requirements *(mandatory)*

- **FR-001**: 负载 MUST 含三协议、尺寸、工具调用、流式、失败、限流、长尾。
- **FR-002**: MUST 使用 500 独立买家/Project/Key；数据集与种子版本化。
- **FR-003**: MUST 提供 baseline、500 RPS/30m、1000 RPS/5m、500 长连接/2h、控制面负载。
- **FR-004**: MUST 注入实例终止、Redis 重启、数据库短断、事件积压、upstream 故障。
- **FR-005**: MUST 采集成功率、平台新增延迟、资源/GC、连接、积压、账务一致性。
- **FR-006**: 500 RPS 30 分钟成功率 ≥99.9%，平台新增 p95 ≤100 ms。
- **FR-007**: 1000 RPS 5 分钟无崩溃/失控积压，降载 10 分钟内恢复基线。
- **FR-008**: 500 SSE/WS 2 小时异常断开 ≤0.5%，内存无无界增长。
- **FR-009**: 故障后符合 SLO/RTO；无越权、重复扣费、丢失账务事件。
- **FR-010**: 压测结束 reservation 可终结；账本重建与请求统计一致。
- **FR-011**: 同一候选连续 3 次达标才可作为发布证据。
- **FR-012**: PostgreSQL RPO ≤5 分钟、RTO ≤30 分钟；Redis 不是 SoR。

### Engineering Requirements

- **ER-001**: `capacity/v1` 契约（profile、门槛、报告 schema）。
- **ER-002**: Gateway 内 mock upstream + 透传内核负载引擎。
- **ER-003**: 故障注入与备份恢复演练代码化；覆盖率 ≥80%。

## Success Criteria

- **SC-001**: 稳态成功率 ≥99.9% 且平台 p95 ≤100 ms。
- **SC-002**: 突发后无崩溃，积压受控并恢复。
- **SC-003**: 500 流断开率 ≤0.5%。
- **SC-004**: 重复扣费次数 = 0，开放 reservation = 0。
- **SC-005**: 备份演练 RPO ≤5 分钟、RTO ≤30 分钟。
- **SC-006**: 连续 3 次运行均达标。

## Assumptions

- 自动化默认跑同一引擎的缩短窗口以保持可重复 CI；完整 30m/5m/2h 由 `CAPACITY_FULL=1` 启用，profile 常量不得缩小。
- 真实厂商冒烟未授权，记为发布阻塞项。
