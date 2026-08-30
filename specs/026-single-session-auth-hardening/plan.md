# Implementation Plan: 单会话与认证安全加固

**Branch**: `026-single-session-auth-hardening` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 SF06 Web 会话之上增加账户会话世代：新登录/全部退出同一事务提升世代并撤销旧会话；引导必须核对世代。权威存储为 PostgreSQL，故跨节点在提交后立即可见（满足 1 秒）。缓存不得作为「有效」依据。新增安全摘要与全部退出。代理 Key 路径不读世代。

## Technical Context

**Language/Version**: Python 3.11.15（api-service）、TypeScript 严格（frontend）

**Primary Dependencies**: SessionService、AuthenticationRepository、HttpOnly cookie、CSRF

**Storage**: PostgreSQL — `users.session_generation`、`auth_sessions.session_generation`（Alembic `0009_session_generation`）

**Testing**: pytest 单元/集成（双设备、重放、CSRF、世代）；Vitest 安全页

**Affected Components**: `services/api-service/`、`frontend/src/`、`shared/contracts/single-session-auth/v1/`

## Constitution Check

### Pre-Research Gate: PASS

世代在权威库；cookie 属性不变；契约先行；无 token 入日志。

### Post-Design Gate: PASS

expand-only 迁移；缓存失败关闭；代理 Key 不耦合。

## Project Structure

```text
shared/contracts/single-session-auth/v1/
services/api-service/alembic/versions/0009_session_generation.py
services/api-service/app/domain/authentication/session_service.py
frontend/src/pages/AccountSecurity.tsx
```

## Complexity Tracking

无宪章违规。
