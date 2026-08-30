# Feature Specification: 分布式认证、路由状态与容量协调

**Feature Branch**: `022-distributed-auth-routing-capacity`

**Created**: 2026-08-31

**Status**: Implemented

**Source Feature**: SF03

## Clarifications

### Session 2026-08-31

- Redis 只保存带 TTL 的热状态；PostgreSQL/绑定表为权威占用。
- 无法判断时失败关闭，不得扩大权限或容量。
- 跨节点 Redis 适配可在无 Redis 时用原子内存后端做单测；运行时 Redis 不可用则拒绝新占用。
- 1 秒撤销：以单调 epoch 传播；节点看到新 epoch 立即拒绝。

## User Scenarios & Testing

### User Story 1 - 专享连接唯一占用 (P1)

20 个并发争抢同一专享连接，只有一个成功。

### User Story 2 - 容量原子预占 (P1)

多调用方合计不超过 limit；重复释放不产生负容量。

### User Story 3 - 撤销失败关闭 (P1)

Key 禁用 epoch 提升后新请求拒绝。存储错误时拒绝而非放行。

### User Story 4 - 重建不越权 (P2)

热状态丢失后从权威绑定重建；不得出现额外占用。

## Requirements

- **FR-001**: 专享占用 MUST 互斥（唯一成功绑定）。
- **FR-002**: 容量预占 MUST 原子，维度含 key/project/connection/protocol。
- **FR-003**: 释放/超时 MUST NOT 使计数为负或永久占用（TTL 或显式 release）。
- **FR-004**: 撤销 epoch MUST 使后续 Allow 为 false。
- **FR-005**: 存储错误 MUST 失败关闭。
- **FR-006**: Redis 不是账本/用户/Binding 事实源。
- **FR-007**: 跨租户 key 不得串用占用。

## Success Criteria

- **SC-001**: 20 并发占用同一连接成功数 = 1。
- **SC-002**: limit=5 时 50 次并发 Incr 成功数 = 5。
- **SC-003**: 存储错误时 Allow=false。
- **SC-004**: 重建后占用集合 ⊆ 权威绑定。

## Assumptions

真实多节点 Redis 故障注入完整矩阵在 SF33 补齐；本 SF 交付可在单进程 race 下证明的原子语义与 Redis 可选适配。
