# Implementation Plan: 容量、压力、耐久与韧性验收

**Branch**: `052-capacity-resilience` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 Gateway 透传内核上用可控 mock upstream 跑版本化 500 租户负载：稳态 500 RPS、突发 1000 RPS、500 长连接、故障注入与账本备份恢复。完整时长是默认 profile；CI 用同一引擎缩短窗口。

## Technical Context

**Language/Version**: Go 1.25.14

**Contracts**: `capacity/v1` 1.0.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；mock 不代表厂商 SLA；账本不可变、失败关闭。

### Post-Design Gate: PASS

无真实付费调用；Redis 非 SoR；专享不回退共享池。
