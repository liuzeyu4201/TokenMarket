# Implementation Plan: 多协议 Provider Binding

**Branch**: `030-provider-binding` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 API Service 落地 Project×protocol 的 Provider Binding：草稿/校验/发布版本，单 active，mode 必须对齐 Project，禁止跨协议，专享 Connection 失效则 degraded 且不回退共享池。发布后替换 SF10 `EmptyBindingLookup`。SDK 提示只含原生入口，不含凭据。Connection/价格走端口。

## Technical Context

**Language/Version**: Python 3.11.15（api-service）、TypeScript（frontend）

**Primary Dependencies**: Project 域、AuthorizationService 工作区透镜、Endpoint Catalog、SF08 UI

**Storage**: PostgreSQL Alembic `0012_provider_bindings`

**Testing**: pytest 并发发布、mode 拒绝、跨协议准入、degraded、启用协议打通；Vitest Binding 表单与 SDK 提示

**Affected Components**: `services/api-service/`、`frontend/src/`、`shared/contracts/provider-binding/v1/`

**Contracts**: 新增 `provider-binding/v1` 1.0.0

**Data & Migrations**: 部分唯一 `(project_id, protocol) WHERE status='active'`；已发布行应用层不 UPDATE 配置字段

**Security & Privacy**: 会话+CSRF；SDK/日志无凭据

**Observability**: binding.published / binding.degraded 审计

## Constitution Check

### Pre-Research Gate: PASS

契约先行；API Service 拥有 Binding；Postgres SoR；测试先行；中文文档。

### Post-Design Gate: PASS

不提前实现 SF14 Connection 表；端口失败关闭。不引入跨协议转换。无新微服务。

## Project Structure

```text
shared/contracts/provider-binding/v1/provider-binding.openapi.yaml
services/api-service/alembic/versions/0012_provider_bindings.py
services/api-service/app/domain/bindings/
services/api-service/app/api/v1/bindings.py
frontend/src/api/v1/bindings.ts
```

## Complexity Tracking

无宪章违规。
