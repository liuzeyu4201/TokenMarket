# 实现计划：用户注册与初始界面

**分支**: `003-user-registration-ui` | **日期**: 2026-07-23 | **规格**: [spec.md](./spec.md)

**输入**: 功能规格来自 `/specs/003-user-registration-ui/spec.md`

## 摘要

交付 SF03 **用户注册**，作为 API Service 上的首个业务能力，并提供 **最小 React 壳层**，使访客可从首页占位导航至注册页，提交手机号/昵称/角色，并看到成功或结构化失败——**不签发会话**（属 SF04）。

技术路径（见 [research.md](./research.md)）：契约优先的 OpenAPI 置于本特性下（实施时提升至 `shared/contracts/user-registration/v1/`）；PostgreSQL `users` + `registration_idempotency_records` 由 API Service 拥有，Alembic expand/backout；大陆手机号规范化纯函数；Redis 固定窗口限流（IP + 手机号），Redis 宕机时 fail-closed；统一包络 `{code,message,data,request_id,timestamp}`；前端 React Router 壳层（`/`、`/register`、`*`）含表单 UX，无 auth store。

## 技术上下文

**语言/版本**: Python 3.11.15（API Service）；TypeScript strict / React 18 / Node 24.18.0（frontend）；PostgreSQL 15.x；Redis 7.x

**主要依赖**: FastAPI + SQLAlchemy asyncio + asyncpg + Alembic + Pydantic v2（既有 api-service 锁 + 经评审的 Redis 客户端增量）；React 18 + Vite + Vitest + Testing Library + React Router（frontend 锁增量）；Gateway **无**业务变更

**存储**: PostgreSQL 为用户与注册幂等（24h 窗口）的事实源。Redis 仅保存短暂的注册限流计数。

**测试**: pytest / pytest-asyncio / httpx（API 单元、真实 PG 集成、并发、迁移 upgrade/downgrade、隐私脱敏、限流）；Vitest + Testing Library（路由、表单状态、错误映射）；OpenAPI/schema 资产契约测试；变更的用户域包 ≥80% 行覆盖率

**目标平台**: 本地开发主机（macOS arm64 / Linux x86_64），API Service 为主机进程，frontend Vite 开发服务器，可用时使用 SF02 本地 PG/Redis；生产镜像路径除新迁移与应用代码外不变

**项目类型**: 多语言 monorepo 特性 — Python 域 API + React SPA 壳层 + 版本化 HTTP 契约 + Alembic 迁移

**性能目标**: 正常本地集成下注册 p95 ≤ 500ms（无 SMS；自动化或环境门控微基准）；注册 UI 在典型开发机上可交互 ≤ 3s，**以手工 quickstart/README 验收**（非 flaky CI 硬门禁）；100 并发同号注册 → ≤1 用户行

**约束**: 无令牌/会话；无密码/邮箱/SMS；无 Gateway 注册代理；业务服务不进 Compose；软删除手机号不得重建；日志/指标/UI 对 PII 脱敏；限流默认 IP 20/15m、手机号 5/15m；幂等 24h；根路径为壳层首页而非注册表单

**规模/范围**: 单一注册端点；两张耐久表；一个 Redis 键命名空间；三条前端路由；一个 OpenAPI 契约包；仅 V0.1 身份基础

**受影响组件**:

| 组件 | 变更 |
|------|------|
| `services/api-service/` | 用户域、注册路由、schemas、repos、限流、迁移、指标、测试 |
| `frontend/` | Router 壳层、home/register/not-found、API 客户端、表单、测试 |
| `shared/contracts/user-registration/v1/` | 提升 OpenAPI + 业务码/规范化文档（实施时） |
| `docs/api/` | 注册契约索引链接 |
| `specs/003-user-registration-ui/contracts/` | 设计期权威源（本计划阶段） |
| `proxy-gateway/`、`billing-service/`、`admin-service/` | **无**功能变更 |

**契约**: [contracts/user-registration.openapi.yaml](./contracts/user-registration.openapi.yaml)、[business-codes.md](./contracts/business-codes.md)、[phone-normalization.md](./contracts/phone-normalization.md)。新增主表面 `user-registration/v1` 为可加性扩展；不修改 health 或 workflow 契约。

**数据与迁移**: 见 [data-model.md](./data-model.md)。Alembic 修订接在 `0001_baseline` 之后；用户+幂等短事务；手机号唯一含软删除；downgrade 已文档化；启动不得自动 migrate。**备份/保留/恢复**: `users` 与 `registration_idempotency_records` 继承 API Service PostgreSQL 实例既有平台备份与非生产 restore 程序；本特性不新增独立备份作业。软删除是业务态，不等于 restore。账户硬删、按时间点恢复用户、以及产品级「账户恢复」均 out of scope。幂等行为 24h 辅助数据（丢失仅影响重放，不影响账户事实）。

**安全与隐私**: 手机号为 PII；响应/日志中脱敏；仅用合成夹具；拒绝客户端提交的 id/status；双维度限流（IP 始终计数；phone 仅在规范化成功后）；统一 `RATE_LIMITED` 包络，不因已注册/软删除状态而变化（防枚举旁路）；注册路径 Redis fail-closed；URL 中无密钥；CORS/本地域仅按 Vite→API 需要配置（配置注入，非硬编码生产）。

**可观测与可靠性**: `X-Request-ID` 关联；注册尝试计数/直方图无高基数手机号标签；DB/Redis 宕机返回 503；客户端在 24h 内用同一幂等键重试。**前端 HTTP**: 单次注册请求超时 **10s**；注册 POST **禁止自动重试**；用户手动重试在成功、过期或新的独立提交前复用同一 `Idempotency-Key`。**告警（必做）**: 交付 Prometheus 告警规则（注册 5xx/`SERVICE_UNAVAILABLE` 升高、限流后端不可用、异常失败率），含 severity、owner = API Service，以及 `ops/` 下 runbook（检测信号、分诊步骤、恢复）；告警/日志保持 PII 脱敏（无完整手机号）。

**部署与回滚**: 迁移与需要新表的 API 镜像一并或先于其发布；回滚 = 停写/切流注册 → 安全时 downgrade 迁移 → 回退镜像；frontend 独立静态部署；在既有 API Service 边界内首批域表无需新 ADR（无新服务）。

## 宪章检查

*门禁：Phase 0 研究前 MUST 通过，Phase 1 设计后 MUST 复核。*

### 研究前门禁

| 门禁 | 状态 | 证据 / 决策 |
|------|------|-------------|
| 架构与所有权 | PASS | API Service 拥有用户域 + DB；frontend 仅展示；无跨服务存储；无新微服务 |
| 契约与兼容 | PASS | OpenAPI + 业务码 + 手机号规范化在实施前定义；包络已版本化 |
| 安全与隐私 | PASS | 无密码/令牌；PII 脱敏；限流；软删除不静默替换；合成测试数据 |
| 数据正确性 | PASS | PG 事实源；手机号唯一；幂等耐久 24h；短事务；仅 Alembic |
| 测试 | PASS | 已规划单元/集成/并发/迁移/隐私/限流/UI 测试；TDD |
| 运维 | PASS | 指标 + request_id；503 fail-closed；告警归属既有服务指标 ownership |
| 交付 | PASS | 锁文件经评审依赖；CI 经既有 make test/lint；可追溯至 quickstart |

无需宪章豁免。（周度 Spec 明文密码条款被宪章与本功能范围 **拒绝**。）

### 设计后门禁

| 门禁 | 状态 | Phase 1 证据 |
|------|------|--------------|
| 架构与所有权 | PASS | [data-model.md](./data-model.md) 所有权；research 决策 1 |
| 契约与兼容 | PASS | [contracts/](./contracts/) OpenAPI + 业务码 + 规范化 |
| 安全与隐私 | PASS | 业务码隐私规则；限流 fail-closed；research 决策 10 脱敏规则 |
| 数据正确性 | PASS | 表、不变量、并发映射、24h 幂等 |
| 测试 | PASS | [quickstart.md](./quickstart.md) 验收矩阵 |
| 运维 | PASS | research + quickstart 中的指标/日志与 503 路径 |
| 交付 | PASS | 迁移/回滚草图；组件列表；契约提升路径 |

设计后结果：**PASS** — 无未解决的产品澄清；可进入 `/speckit-tasks` 实施。

## 项目结构

### 文档（本特性）

```text
specs/003-user-registration-ui/
├── spec.md
├── plan.md                 # This file
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── user-registration.openapi.yaml
│   ├── business-codes.md
│   └── phone-normalization.md
└── tasks.md                # /speckit-tasks (not this command)
```

### 源码（仓库根）— 实施目标布局

```text
services/api-service/
├── alembic/versions/0002_*.py          # users + idempotency
├── app/
│   ├── main.py                         # mount router
│   ├── schemas/                        # envelope, register DTOs
│   ├── domain/users/                   # normalize, service rules
│   ├── repositories/                   # user + idempotency
│   ├── api/v1/auth.py                  # POST /api/v1/auth/register
│   ├── rate_limit.py                   # Redis fixed window
│   └── observability.py                # registration metrics
└── tests/
    ├── unit/
    ├── integration/
    └── test_register_*.py

frontend/src/
├── main.tsx
├── App.tsx                             # Router provider
├── layouts/AppShell.tsx
├── pages/Home.tsx
├── pages/Register.tsx
├── pages/NotFound.tsx
├── api/client.ts
├── api/v1/auth.ts
├── types/auth.ts
└── styles/…                            # minimal CSS

shared/contracts/user-registration/v1/  # promoted copies at implement
docs/api/README.md                      # index entry
```

**结构决策**: 域逻辑保留在既有 `api-service` 包边界内（handlers → domain → repository）。Frontend 向已文档化的 `pages/` / `api/` 布局演进，不拉入完整市场 UI。契约先在特性目录编写，再提升至 `shared/contracts`，以便 CI 契约校验拥有稳定路径。

## 复杂度跟踪

> 无需要豁免的宪章违规。

| 违规 | 为何需要 | 被否决的更简方案 | ADR / Owner | 控制 | 评审或到期 |
|------|----------|------------------|-------------|------|------------|
| — | — | — | — | — | — |

## Phase 0 与 1 产出

| 产物 | 路径 |
|------|------|
| 研究 | [research.md](./research.md) |
| 数据模型 | [data-model.md](./data-model.md) |
| 契约 | [contracts/](./contracts/) |
| 快速验收 | [quickstart.md](./quickstart.md) |

## Agent 上下文

本仓库无 `.specify` agent-context 更新脚本；活动特性指针仍为 `.specify/feature.json` → `specs/003-user-registration-ui`。实施者应遵循 `CLAUDE.md` / 宪章与本计划。

## 下一命令

```text
/speckit-tasks
```
