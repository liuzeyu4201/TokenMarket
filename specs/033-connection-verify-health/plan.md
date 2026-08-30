# Implementation Plan: 连接验证、能力发现与健康状态

**Branch**: `033-connection-verify-health` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 SF14 Connection 上增加可注入 VendorProbe、与 Endpoint Catalog 求交的版本化能力快照、带滞后的健康状态机、全局探测预算与手动复验。公开路径不解密。扩展 `provider-connection/v1` 至 1.2.0。

## Technical Context

**Language/Version**: Python 3.11.15、TypeScript

**Primary Dependencies**: ConnectionService.unwrap(purpose=verify)、Endpoint Catalog、Authorization 卖家工作区

**Storage**: Alembic `0015_connection_health`

**Testing**: pytest 六类结果、快照交集、滞后、1000 连接预算、脱敏；Vitest 健康展示与复验

**Contracts**: `provider-connection/v1` 1.2.0 expand-only

**Security**: 内部 unwrap；诊断脱敏；探测走既有 SSRF；默认夹具 fail-closed

**Scale/Scope**: 调度 tick 全局并发默认 8；1000 连接预算测试

## Constitution Check

### Pre-Research Gate: PASS

契约先行；不新增独立健康服务（同一 API Service 域）；密钥不入诊断。

### Post-Design Gate: PASS

VendorProbe 为域内端口而非新进程。不实现厂商控制面。不付费调用真实上游。

## Complexity Tracking

无宪章违规。
