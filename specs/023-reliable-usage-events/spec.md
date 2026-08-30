# Feature Specification: 可靠用量事件投递与重放

**Feature Branch**: `023-reliable-usage-events`
**Created**: 2026-08-31
**Status**: Implemented
**Source Feature**: SF04

## Clarifications

- 至少一次投递 + 按 event_id 幂等 = 效果一次。
- 禁止仅内存队列作为唯一副本；本 SF 使用可持久化 outbox（文件/后续 DB）。
- 事件不含明文密钥或完整请求正文。
- 队列不可用不得静默丢弃。

## User Stories

### US1 生命周期事件 (P1)
成功、4xx/5xx、超时、客户端中断各产生带序号的事件。

### US2 幂等消费 (P1)
同一事件重复 10 次，计数器 +1 而非 +10。

### US3 死信与重放 (P1)
超过失败阈值进入 DLQ，可重放；重放后离开 DLQ。

### US4 schema (P2)
事件含 event_id、request_id、versions、protocol、endpoint、status；未知字段消费者忽略。

## Requirements

- **FR-001**: Append 必须持久化；失败返回错误不得假装成功。
- **FR-002**: Consume 按 event_id 幂等。
- **FR-003**: 同一 request_id 事件 seq 单调。
- **FR-004**: 失败达阈值进入 dead letter。
- **FR-005**: ReplayDeadLetter 可再次投递。
- **FR-006**: payload 禁止 api_key/authorization/raw_body 字段。

## Success Criteria

- **SC-001**: 四类终态各至少一条事件。
- **SC-002**: 重复 10 次消费效果与 1 次相同。
- **SC-003**: DLQ 重放成功后 pending 中可见且不再停在 DLQ。
