# Implementation Plan: 买家卖家工作区切换与路由授权

**Branch**: `028-workspace-switch-authorization` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 Web 会话上增加 `workspace`。授权在账户角色上限内按会话工作区求交。切换走 CSRF 保护 HTTP。前端 both 可切换并清空上一工作区草稿。自路由排除补 10 万次属性测试。

## Technical Context

**Language/Version**: Python 3.11（api-service）、TypeScript（frontend）

**Primary Dependencies**: SessionService、AuthorizationService、role-access-isolation 矩阵

**Storage**: PostgreSQL `auth_sessions.workspace`；Alembic `0010_session_workspace`

**Testing**: pytest 授权矩阵/越权/切换；100k 自排除；Vitest 壳层切换

**Affected Components**: `services/api-service/`、`frontend/src/`、`shared/contracts/workspace-switch/v1/`

## Constitution Check

### Pre-Research Gate: PASS

身份只来自会话；忽略客户端身份字段；expand-only 迁移；审计无 token。

### Post-Design Gate: PASS

工作区不能提权；管理员不走普通工作区。

## Project Structure

```text
shared/contracts/workspace-switch/v1/
services/api-service/alembic/versions/0010_session_workspace.py
services/api-service/app/domain/authorization/
frontend/src/layouts/AppShell.tsx
```

## Complexity Tracking

无宪章违规。
