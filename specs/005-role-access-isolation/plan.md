# Implementation Plan：角色授权与自买自卖隔离

**Branch**: `005-role-access-isolation` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)

**Input**: `specs/005-role-access-isolation/spec.md`

**Plan revision**: 2026-08-01 — 对齐 analyze 收口后规格（I1 审计先落盘、I2 性能分层、
U1 批量范围外、C1 会话撤销、revoke→disabled）。

## Summary

在 API Service 内交付服务端默认拒绝的角色权限矩阵、**单资源**所有权校验、自买自卖
（自路由）排除与强制脱敏审计，支撑 `buyer` / `seller` / `both` 在声明动作族上的
最小权限边界。身份仅来自 SF04 会话用户 ID；**每次**授权从 PostgreSQL `users`
读取当前角色与账户状态；会话缺失/过期/撤销在矩阵之前失败为 `UNAUTHENTICATED`。

完整卖家/代理 Key 产品 API、批量授权 API、授权加速层 **不在** V0.1 交付范围；以轻量
`resource_ownerships` 与非生产夹具 + `evaluate` / `exclude-self` 完成矩阵、IDOR、
自排除与审计验收。Gateway / Frontend / Billing / Admin 本功能无业务接线。

技术路径见 [research.md](./research.md)：`AuthorizationService` 单一入口、
`authz-matrix-v1` 表驱动、统一 404、**拒绝前先提交审计意图否则 503**、直读为主
fail-closed。

## Technical Context

**Language/Version**: Python 3.11.15（API Service）；既有 Go Gateway / React 本功能
无代码变更要求

**Primary Dependencies**: FastAPI、SQLAlchemy 2 asyncio、asyncpg、Alembic、Pydantic v2、
pytest / pytest-asyncio / testcontainers（PostgreSQL）；复用 SF04 会话校验与写保护
（Origin/CSRF 用于状态变更夹具）。不引入 Casbin/OPA/JWT 授权框架。

**Storage**: PostgreSQL 15 为用户角色/状态、资源所有权、授权审计（及 outbox）事实源。
**不实现** Redis 授权加速（范围外）；若未来启用须 ≤1s 失效且 fail-closed 回源。

**Testing**: 表驱动单元矩阵；真实 PostgreSQL 集成；负向 IDOR/伪造身份/账户停用/
**会话撤销→401**；并发角色与所有权变更；审计意图落盘失败→503；授权域 ≥80% 行覆盖；
自排除 1000 次零命中；SC-004a 微基准 env 门控。

**Target Platform**: Linux 服务端与本地 macOS/Linux 主机进程（`make start`）；无新 Compose
业务服务。

**Project Type**: monorepo 领域增量 — Python API Service + 版本化 HTTP/决策契约

**Performance Goals**:

| 路径 | 目标 | Spec |
|------|------|------|
| 默认直读 | P95 ≤50ms | SC-004a / ER-004a |
| 加速命中（若未来启用） | P95 ≤10ms | SC-004b / ER-004b |
| 任意故障 | fail-open = 0 | SC-004c / ER-004c |
| 角色/所有权变更可见性 | ≤1s | SC-003 / FR-009 |

**Constraints**: 默认拒绝；客户端身份字段忽略；跨用户统一 `RESOURCE_NOT_FOUND`；
自排除无降级；事实源/审计意图失败 fail-closed（意图失败→503 非裸 403）；
夹具仅 local/test；无前端；无管理员 RBAC；无完整 Key 密钥材料；**无批量 API**；
`proxy_key.revoke` → `disabled`。

**Scale/Scope**: 8 个声明动作、1 个 policy 版本、3 张新表、evaluate + exclude-self +
fixtures HTTP、1 次 additive 迁移；无新微服务。

### Affected Components

| Component | Owner / Planned change | Explicit non-change |
|-----------|------------------------|---------------------|
| `services/api-service/` | `domain/authorization/`、仓储、依赖注入、evaluate/exclude-self/fixtures、迁移、指标、审计、测试 | 不跨服务读库；不实现完整 Key 加密与产品 CRUD；不实现加速层 |
| `shared/contracts/role-access-isolation/v1/` | 实现时提升本目录契约 | 不修改 registration/phone-auth 语义 |
| `ops/alerts/`、`ops/runbooks/`（按需） | 授权 503、审计积压信号与分诊 | 不新增公开 Make 动作 |
| `frontend/` | 无 | 无权限 UI |
| `proxy-gateway/`、`billing-service/`、`admin-service/` | 无 | 不复制 RBAC |

**Contracts**: 设计契约位于

- [role-access-isolation.openapi.yaml](./contracts/role-access-isolation.openapi.yaml)
- [business-codes.md](./contracts/business-codes.md)
- [authorization-matrix.md](./contracts/authorization-matrix.md)

实现时发布到 `shared/contracts/role-access-isolation/v1/` 后再接消费者。

**Data & Migrations**: 见 [data-model.md](./data-model.md)。迁移
`0004_role_access_isolation` additive。授权读 `users` + `auth_sessions`（仅校验会话）；
写 ownership/events 短事务；**返回业务拒绝前**必须成功提交 event 或 pending outbox。
常规回滚停用夹具与新路由，保留表与审计。

**Security & Privacy**: 服务端最小权限；会话仅证身份（FR-006a）；统一 404；审计脱敏；
夹具生产关闭；负向 IDOR/伪造字段/会话撤销测试；合成数据；写夹具复用 SF04 CSRF/Origin。

**Observability & Reliability**: 指标按 `action`/`result`/`reason_code`（低基数）；
`request_id` 关联；DB 故障与审计意图失败均 503；可选 outbox 积压告警；无密钥标签。

**Deployment & Rollback**: 契约与迁移 → API 镜像 → 验证夹具在 prod 关闭 → 矩阵/quickstart
证据（含 SC-006）。回滚：关闭路由/配置 → 回退镜像；表保留。根 Makefile 仍为唯一公开
工作流入口。

## Constitution Check

*GATE: Phase 0 前通过；Phase 1 设计后复核（含规格收口后复核）。*

### Pre-Research Gate

| Gate | Result | Planned evidence |
|------|--------|------------------|
| Architecture and ownership | PASS | 仅 API Service 拥有授权事实；无跨服务存储；无新服务 |
| Contracts and compatibility | PASS | OpenAPI + 业务码 + 矩阵在实现前定义 |
| Security and privacy | PASS | 默认拒绝、统一 404、审计先落盘、会话撤销 401、夹具隔离 |
| Data correctness | PASS | PG 事实源；ownership 唯一；事件追加；Alembic additive |
| Testing | PASS | 矩阵/IDOR/会话撤销/并发/审计 503/覆盖率规划 |
| Operations | PASS | 指标、503、可选 outbox 积压、request_id |
| Delivery | PASS | 既有 make ci；迁移/回滚草图 |
| Documentation language | PASS | 人工文档简体中文；契约标识英文 |

无宪章豁免。

### Post-Design Gate

| Gate | Result | Design evidence |
|------|--------|-----------------|
| Architecture and ownership | PASS | [research.md](./research.md) D1/D10；Affected Components |
| Contracts and compatibility | PASS | [contracts/](./contracts/)；FR-011 批量标范围外 |
| Security and privacy | PASS | research D3/D6/D8/D9；FR-010a 先意图后拒绝；FR-006a |
| Data correctness | PASS | [data-model.md](./data-model.md)；revoke→disabled |
| Testing | PASS | [quickstart.md](./quickstart.md) SC-001–006；[tasks.md](./tasks.md) T021/T046/T050 |
| Operations | PASS | research D8/D11；503 与审计积压 |
| Delivery | PASS | 迁移命名、夹具开关、回滚；tasks 已存在 |
| Documentation language | PASS | Phase 0/1 中文主体 |

设计后结果：**PASS** — 澄清 + analyze 收口已闭合；`tasks.md` 已对齐；可进入
`/speckit-implement`（若任务清单需再生成可先 `/speckit-tasks`）。

## Project Structure

### Documentation (this feature)

```text
specs/005-role-access-isolation/
├── spec.md
├── plan.md                 # 本文件（收口后刷新）
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── contracts/
│   ├── role-access-isolation.openapi.yaml
│   ├── business-codes.md
│   └── authorization-matrix.md
├── checklists/
│   └── requirements.md
└── tasks.md                # 已存在；含 T021 会话撤销 / T046·T050 审计顺序
```

### Source Code (repository root)

```text
services/api-service/
├── app/
│   ├── api/v1/
│   │   └── authorization.py          # evaluate / exclude-self / fixtures
│   ├── domain/
│   │   ├── users/                    # 既有；授权只读
│   │   ├── authentication/           # 既有会话；仅取 user_id / 撤销校验
│   │   └── authorization/            # 矩阵、Decision、服务、纯排除、审计
│   ├── repositories/
│   │   └── authorization.py
│   ├── schemas/
│   │   └── authorization.py
│   ├── dependencies.py               # 仅 user_id+session_id；禁止 role_snapshot 授权
│   └── observability.py              # 授权计数指标
├── alembic/versions/
│   └── 0004_role_access_isolation.py
└── tests/
    ├── unit/
    ├── contract/
    └── integration/                  # 含 session revoke、audit fail → 503

shared/contracts/role-access-isolation/v1/   # 实现时提升
```

**Structure Decision**: 授权作为 API Service 一等领域包；HTTP 以契约评估与夹具为主；
不交付加速层与批量 API。

## Complexity Tracking

> 无宪章违规，无需豁免表。

| Violation | Why Needed | Simpler Alternative Rejected | ADR / Owner | Controls | Review or Expiry |
|-----------|------------|------------------------------|-------------|----------|------------------|
| — | — | — | — | — | — |

## Phase 0 / Phase 1 Outputs

| Artifact | Path | Status |
|----------|------|--------|
| Research | [research.md](./research.md) | Complete（含 D8 I1 / 性能与范围外） |
| Data model | [data-model.md](./data-model.md) | Complete（先意图后拒绝；revoke→disabled） |
| Contracts | [contracts/](./contracts/) | Complete |
| Quickstart | [quickstart.md](./quickstart.md) | Complete（SC-001–006） |
| Tasks | [tasks.md](./tasks.md) | Complete（先于本轮 plan 刷新已存在） |

## Spec alignment notes (post-analyze)

| 主题 | 计划落点 |
|------|----------|
| FR-010a 审计顺序 | 领域服务返回前 commit event/outbox；失败 503；T046/T050 |
| SC-004a/b/c | 默认仅验收 a+c；b 仅当启用加速；T057/T024 |
| FR-011 批量 | 无实现、无任务 |
| FR-006a / SC-006 | 会话依赖失败即 401；T021 |
| revoke | lifecycle `disabled` |

## Next

1. 推荐：`/speckit-implement` 按 [tasks.md](./tasks.md) 执行（T001 起）  
2. 可选：若希望任务清单再生成一遍，运行 `/speckit-tasks`  
3. 可选：`/speckit-analyze` 复核收口后一致性  
