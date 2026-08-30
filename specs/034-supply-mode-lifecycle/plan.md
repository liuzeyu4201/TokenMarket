# Implementation Plan: 共享/专享供给模式与连接生命周期

**Branch**: `034-supply-mode-lifecycle` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 Provider Connection 上增加 lifecycle_state 状态机、上架锁定模式、pause/drain/retire、删除阻塞清单，以及共享/专享路由可见性隔离。扩展 `provider-connection/v1` 1.3.0。专享 Binding 部分唯一索引保证一连接一活动绑定。

## Technical Context

**Language/Version**: Python 3.11.15、TypeScript

**Primary Dependencies**: ConnectionService、HealthService.admits_new、BindingStore.list_by_connection

**Storage**: Alembic `0016_supply_lifecycle`

**Testing**: pytest 转换矩阵、阻塞、pause≤1s、池隔离、专享 unique；Vitest 生命周期按钮

**Contracts**: `provider-connection/v1` 1.3.0 expand-only

**Security**: 卖家工作区写路径 CSRF；无明文

## Constitution Check

### Pre-Research Gate: PASS

契约先行；不新增服务；模式与绑定约束落在 Postgres。

### Post-Design Gate: PASS

在途/未结算为端口而非新账本服务。不实现共享回退。

## Complexity Tracking

无宪章违规。
