# Implementation Plan: 分布式认证、路由状态与容量协调

**Branch**: `022-distributed-auth-routing-capacity` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 Gateway 领域包 `coord` 实现原子容量预占、专享占用互斥、撤销 epoch 与失败关闭。内存后端供 race 证明；Redis 丢失时不得放宽权限。权威绑定重建不得发明占用。

## Technical Context

**Language/Version**: Go 1.25.14  
**Storage**: 进程内原子 map（热状态语义）；Redis 作为后续可插拔 Backend，本 SF 不把 Redis 当 Binding/账本事实源。  
**Testing**: `go test -race`；20 并发占用；容量 limit。

## Constitution Check

PASS：无跨服务读库；coord 在 gateway 领域；失败关闭；测试先于实现。

## Complexity Tracking

无。
