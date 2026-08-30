# Implementation Plan: 可靠用量事件投递与重放

**Branch**: `023-reliable-usage-events` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

Gateway `usageoutbox` 文件 outbox：Append 持久化、按 event_id 幂等 Drain、失败进 DLQ 可重放。契约 `shared/contracts/usage-outbox/v1/`。

## Constitution Check

PASS：事件信封完整；禁止敏感字段；非仅内存队列；测试先行。
