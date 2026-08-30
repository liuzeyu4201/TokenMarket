# Implementation Plan: 买家 Project 生命周期与模式

**Branch**: `029-buyer-project-lifecycle` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/029-buyer-project-lifecycle/spec.md`

## Summary

在 API Service 落地买家 Project 作为隔离、授权与后续 Binding/Key/路由的根。创建时必须选择不可变 `shared|dedicated`；状态机 `draft|active|suspended|archived`；创建可声明协议集合，创建后启用协议经 Binding 端口失败关闭（SF11 前恒为无 Binding）。删除读阻塞表；归档后准入函数立即拒绝新代理请求。扩展既有 `project/v1`（expand-only，PATCH 无 mode）。买家工作区 UI `/projects` 使用设计系统组件。

## Technical Context

**Language/Version**: Python 3.11.15（api-service）、TypeScript 严格模式（frontend）

**Primary Dependencies**: FastAPI、SQLAlchemy、Alembic、AuthorizationService 工作区透镜、SF08 UI kit

**Storage**: PostgreSQL 15 为 SoR。Alembic `0011_buyer_projects`：`projects`、`project_protocols`、`project_runtime_blockers`、`project_idempotency`、`project_audit_events`。Redis 不保存 Project 事实。

**Testing**: pytest 领域/HTTP/迁移/并发/IDOR；Vitest 列表与创建表单。归档准入在同一事务提交后立即断言（≤1s）。

**Target Platform**: API Service + React 买家工作区

**Project Type**: monorepo 领域增量（非新服务）

**Performance Goals**: 归档后准入检查 ≤1s（直读 Postgres，无缓存）

**Constraints**: mode 应用层与触发器双拒绝；IDOR 同形 `NOT_FOUND`；卖家工作区 403；无 Binding/Key/账本实体实现

**Scale/Scope**: 单账号少量 Project；协议枚举 openai/anthropic/vertex

**Affected Components**: `services/api-service/`、`frontend/src/`、`shared/contracts/project/v1/`、`shared/contracts/role-access-isolation/v1/`（动作枚举 expand-only）

**Contracts**: 扩展 `project/v1` 至 1.1.0（兼容增量：列表/PATCH 名称/状态机/协议启用停用/删除阻塞/准入）。不新增 catalog 目录。

**Data & Migrations**: 账号内 `lower(btrim(display_name))` 部分唯一（未删除）；mode CHECK + BEFORE UPDATE 触发器；幂等键作用于创建。回退 drop 0011 对象，不影响 users/sessions。

**Security & Privacy**: 身份仅会话；写操作 CSRF+Origin；所有者隔离；审计无秘密。

**Observability & Reliability**: 创建/归档/删除写 `project_audit_events` 与结构化日志（owner、project_id、request_id）。

**Deployment & Rollback**: Alembic 0011 随 api-service；回退 `downgrade 0010_session_workspace`。

## Constitution Check

### Pre-Research Gate: PASS

- 所有权在 API Service Project 域；网关本 SF 不读库。
- 先扩展 OpenAPI 再实现消费者。
- 会话身份 + 工作区透镜 + IDOR 404 + CSRF。
- Postgres SoR、约束、幂等、可回退迁移。
- 测试先行：状态机、mode、Binding 失败关闭、删除阻塞、IDOR、准入计时。
- 审计红acted；无新密钥。
- 中文规格/计划/任务。

### Post-Design Gate: PASS

- Binding 为端口，默认空实现恒 False，不提前实现 SF11。
- 阻塞表供后续 SF 写入；本 SF 可读并拒绝删除。
- 不新增微服务或跨库双写。
- PATCH schema `additionalProperties: false` 且无 mode 字段。

## Project Structure

### Documentation (this feature)

```text
specs/029-buyer-project-lifecycle/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
├── tasks.md
└── evidence/
```

### Source Code

```text
shared/contracts/project/v1/project.openapi.yaml
services/api-service/alembic/versions/0011_buyer_projects.py
services/api-service/app/domain/projects/
services/api-service/app/api/v1/projects.py
services/api-service/app/repositories/projects.py
frontend/src/pages/Projects.tsx
frontend/src/pages/ProjectDetail.tsx
frontend/src/api/v1/projects.ts
```

**Structure Decision**: 扩展既有 `project/v1` 与 api-service 域包；不新建服务。

## Complexity Tracking

无宪章违规。
