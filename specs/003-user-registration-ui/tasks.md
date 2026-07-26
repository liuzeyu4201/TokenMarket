# 任务：用户注册与初始界面

**输入**: 设计文档来自 `/specs/003-user-registration-ui/`

**前置**: `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`

**测试**: 每次行为变更均 **必须** 编写测试，并在对应实现任务前观察到失败。`services/api-service/app/domain/` 下的域包与注册 handlers 要求 ≥80% 行覆盖率，并对唯一性、幂等、并发、限流与 PII 脱敏做直接负向覆盖。

**组织**: 任务按用户故事（US1–US3）分组。Setup 与 Foundational 阻塞全部故事。MVP = Phase 1–3（US1 端到端经 UI + API 成功路径注册）。US2 加固安全；US3 在 US1 所需最小导航之上完成壳层/无障碍打磨。

**UI 壳层边界（分析 I2 / 选项 A）**:

- **US1 拥有** 成功路径所需的最小可导航壳层：`AppShell` 含首页 + 注册链接、`Home` 占位（非表单）、`/` 与 `/register` 路由、注册表单 + 成功态。US1 **不要** 实现 catch-all `*`、完整无障碍打磨或窄视口 CSS，除非基本可用性必需。
- **US3 拥有** NotFound / 暂未开放（`*`）、语义化无障碍 refinement、使提交按钮保持可见的响应式 CSS，以及 `frontend/README.md` 路由说明。US3 可编辑与 US1 相同的文件，但仅限上述增量——避免从零重写 Home/Register。

## 格式：`[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件，同批次无未完成任务依赖）
- **[Story]**: 映射 `spec.md` 用户故事 1/2/3（`[US1]`、`[US2]`、`[US3]`）
- 每个任务须点名其创建或修改的精确文件路径

## 路径约定

- API: `services/api-service/`
- Frontend: `frontend/`
- 共享契约: `shared/contracts/user-registration/v1/`
- 特性契约（源）: `specs/003-user-registration-ui/contracts/`

---

## Phase 1: Setup（共享基础设施）

**目的**: 物化契约、锁定经评审依赖、搭建包目录骨架，尚无业务行为。

- [x] T001 将特性契约提升至版本化共享路径：复制 `specs/003-user-registration-ui/contracts/user-registration.openapi.yaml`、`business-codes.md` 与 `phone-normalization.md` 到 `shared/contracts/user-registration/v1/`，并在 `shared/contracts/README.md` 登记所有权/版本
- [x] T002 [P] 在 `docs/api/README.md` 为注册契约建立索引，链接到 `shared/contracts/user-registration/v1/`
- [x] T003 向 `services/api-service/pyproject.toml` 添加经评审的 Redis 异步客户端依赖，并刷新 `services/api-service/uv.lock`，不改无关 pin
- [x] T004 [P] 向 `frontend/package.json` 添加 `react-router-dom`（及所需 types），并刷新 `frontend/package-lock.json`
- [x] T005 [P] 在 `services/api-service/app/schemas/`、`services/api-service/app/domain/users/`、`services/api-service/app/repositories/`、`services/api-service/app/api/v1/` 下创建 API 包骨架（仅空模块 / `__init__.py`）
- [x] T006 [P] 在 `frontend/src/layouts/`、`frontend/src/pages/`、`frontend/src/api/`、`frontend/src/api/v1/`、`frontend/src/types/`、`frontend/src/styles/` 下创建 frontend 包骨架
- [x] T007 [P] 为 `user-registration/v1` 在 `shared/tests/test_contract_assets.py` 添加契约资产存在/schema 冒烟测试（或扩展既有校验覆盖）

**检查点**: 契约可发现；依赖已锁；空包存在；尚无注册行为。

---

## Phase 2: Foundational（阻塞性前置）

**目的**: 全部故事所需的统一包络、持久化会话、迁移、Redis 接线与测试工厂。

**关键**: 本阶段通过前不得开始任何用户故事实现。先写 foundational 测试，并在断言缺失行为处观察到失败。

- [x] T008 [P] 在 `services/api-service/tests/unit/test_envelope_schemas.py` 添加统一 API 包络模型（`code`、`message`、`data`、`request_id`、`timestamp`）的失败测试
- [x] T009 [P] 在 `services/api-service/tests/integration/test_users_migration.py` 添加 users + registration_idempotency 表 upgrade/downgrade 的失败迁移测试
- [x] T010 [P] 在 `services/api-service/tests/unit/test_phone_normalization.py` 按 `contracts/phone-normalization.md` 添加大陆手机号规范化矩阵的失败单元测试
- [x] T011 在 `services/api-service/app/schemas/envelope.py` 实现 `BaseResponse` / 错误包络 Pydantic 模型，直至 T008 通过
- [x] T012 在 `services/api-service/app/domain/users/phone.py` 实现 `normalize_cn_mobile` 纯函数与校验错误，直至 T010 通过
- [x] T013 在 `services/api-service/alembic/versions/0002_users_registration.py` 添加 Alembic 修订：创建 ENUM `user_role`/`user_status`、表 `users`、表 `registration_idempotency_records`、唯一/检查/FK，直至 T009 通过
- [x] T014 在 `services/api-service/app/domain/users/models.py` 实现 User 与 RegistrationIdempotencyRecord 的 SQLAlchemy 模型，对齐 `data-model.md`
- [x] T015 在 `services/api-service/app/dependencies.py` 实现异步 session 依赖工厂（应用级 engine 复用、请求级 session），必要时在 `services/api-service/app/main.py` 接线 lifespan，启动时不自动 migrate
- [x] T016 [P] 在 `services/api-service/app/rate_limit.py` 实现 Redis 客户端配置与 fail-closed 辅助桩，并在 `.env.example` 文档化 `REDIS_URL` 占位
- [x] T017 [P] 在 `services/api-service/app/observability.py` 扩展注册指标辅助（尝试总数、耗时直方图、限流计数；无手机号标签）
- [x] T018 在 `services/api-service/tests/conftest.py` 建立集成夹具：可丢弃 PG schema、合成手机号、幂等键工厂、可选 Redis 假/真切换
- [x] T019 [P] 在 `frontend/.env.development` 示例或 `frontend/` 下已文档化的 `.env.example` 中添加 API 基址环境占位（如 `VITE_API_BASE_URL`），不提交密钥

**检查点**: 迁移可应用/回滚；包络 + 手机号规范化已测；session/Redis/指标钩子存在；可开始故事。

---

## Phase 3: User Story 1 - 通过界面完成首次注册 (Priority: P1) 🎯 MVP

**目标**: 未认证访客可从应用壳层到达注册页，提交合法手机号/昵称/角色，创建一条 active 用户，并看到成功确认（无令牌/会话）。

**独立测试**: 启动 API（已迁移）+ frontend；从 `/` 导航至 `/register`；提交未占用大陆手机号 + 昵称 + 角色；UI 显示 user_id/角色成功与“尚未登录”；DB 恰好一条匹配的 `users` 行含审计字段。

### User Story 1 的测试（先写并观察到失败）

- [x] T020 [P] [US1] 在 `services/api-service/tests/unit/test_registration_validation.py` 添加请求哈希规范化与昵称校验规则的单元测试
- [x] T021 [P] [US1] 在 `services/api-service/tests/unit/test_registration_service.py` 添加 repository/service 成功路径单测：单事务创建用户 + 幂等行
- [x] T022 [P] [US1] 在 `services/api-service/tests/integration/test_register_api.py` 添加 `POST /api/v1/auth/register` 成功包络与头的 HTTP 契约/集成测试
- [x] T023 [P] [US1] 在 `services/api-service/tests/unit/test_registration_privacy.py` 添加隐私测试：成功体/日志永不含完整手机号明文
- [x] T024 [P] [US1] 在 `frontend/src/pages/Register.test.tsx` 与 `frontend/src/api/v1/auth.test.ts` 添加前端测试：注册表单渲染、客户端必填提示、成功态、`code=0` 解析，以及 **10s 超时 / 无自动重试** 行为
- [x] T025 [P] [US1] 在 `frontend/src/App.test.tsx`（或 `frontend/src/pages/Home.test.tsx`）添加前端冒烟：`/` 不是注册表单，并暴露注册导航/链接

### User Story 1 的实现

- [x] T026 [P] [US1] 在 `services/api-service/app/schemas/register.py` 实现与 OpenAPI 对齐的注册请求/响应 DTO
- [x] T027 [P] [US1] 在 `services/api-service/app/repositories/users.py` 与 `services/api-service/app/repositories/idempotency.py` 实现用户与幂等 repository
- [x] T028 [US1] 在 `services/api-service/app/domain/users/service.py` 实现 `RegistrationService.register` 成功路径（规范化 → insert active 用户 → insert 24h 幂等 → commit）
- [x] T029 [US1] 在 `services/api-service/app/api/v1/auth.py` 实现 `POST /api/v1/auth/register` 路由：要求 `Idempotency-Key`、包络映射、不签发令牌
- [x] T030 [US1] 在 `services/api-service/app/main.py` 挂载 v1 auth 路由，并确保本地 Vite origin 的 CORS 可配置
- [x] T031 [P] [US1] 在 `frontend/src/api/client.ts`、`frontend/src/api/v1/auth.ts` 与 `frontend/src/types/auth.ts` 实现类型化 API 客户端 + `registerUser`：**10s 请求超时**、注册 POST **无自动重试**、`AbortSignal`/错误映射
- [x] T032 [US1] 在 `frontend/src/layouts/AppShell.tsx` 与 `frontend/src/styles/globals.css` 实现 **最小** App 壳层布局：仅导航链接（首页、注册）——尚无 NotFound 路由——及基线样式
- [x] T033 [US1] 在 `frontend/src/pages/Home.tsx` 实现首页占位页（非注册表单）
- [x] T034 [US1] 在 `frontend/src/pages/Register.tsx` 实现注册页：手机号/昵称/角色（**无默认角色—用户必须选择**）、生成 `Idempotency-Key`、提交、忙碌态、成功确认（user_id、角色、尚未登录文案、仅脱敏手机号）
- [x] T035 [US1] 在 `frontend/src/App.tsx` 与 `frontend/src/main.tsx` 接线 React Router 路由：仅 `/` 与 `/register`（`*` 延后至 US3）
- [x] T036 [US1] 重跑 US1 测试至绿；确认变更域包覆盖率门禁

**检查点**: MVP 演示路径端到端成功注册可用；负向/滥用路径可能仍不完整。

---

## Phase 4: User Story 2 - 安全处理重复与非法注册 (Priority: P1)

**目标**: 重复、并发、校验失败、软删除号、幂等冲突/过期与限流永不创建额外账户或泄露 PII；UI 展示字段/表单错误，含忙碌与限流态。

**独立测试**: 并发同号注册 → ≤1 用户；同键重放 → 同一 user_id；占用号 → `PHONE_ALREADY_REGISTERED`；软删号 → `ACCOUNT_UNAVAILABLE`；非法字段 → `VALIDATION_ERROR`；限流突发 → `RATE_LIMITED`；UI 映射各类错误且无其他账户 PII。

### User Story 2 的测试（先写并观察到失败）

- [x] T037 [P] [US2] 在 `services/api-service/tests/unit/test_registration_validation.py` 添加字段校验错误（phone/nickname/role/幂等键）映射至 `VALIDATION_ERROR` 的单元测试
- [x] T038 [P] [US2] 在 `services/api-service/tests/integration/test_register_conflicts.py` 添加活跃号冲突 vs 软删除 `ACCOUNT_UNAVAILABLE` 测试
- [x] T039 [P] [US2] 在 `services/api-service/tests/integration/test_register_idempotency.py` 添加幂等测试：同键同体重放、同键异体冲突、24h 后过期键（时钟夹具）
- [x] T040 [P] [US2] 在 `services/api-service/tests/integration/test_register_concurrency.py` 添加并发测试：100 并行同规范化号注册 → 一条用户行
- [x] T041 [P] [US2] 在 `services/api-service/tests/integration/test_register_rate_limit.py` 添加限流测试：IP 20/15m 与 phone 5/15m、Redis 不可用 fail-closed 503，以及 **防枚举** 用例（非法 vs 合法号计数规则；`RATE_LIMITED` 体/码不因占用/软删/未知号而变化）
- [x] T042 [P] [US2] 在 `services/api-service/tests/integration/test_register_failures.py` 添加 DB 不可用 / 事务回滚测试，确保无部分用户
- [x] T043 [P] [US2] 在 `frontend/src/pages/Register.test.tsx` 添加前端测试：字段错误、占用 vs 不可用文案、限流横幅、提交忙碌禁用、request_id 展示

### User Story 2 的实现

- [x] T044 [US2] 在 `services/api-service/app/domain/users/service.py` 扩展 `RegistrationService`：校验顺序、唯一性冲突映射、软删除分支、幂等冲突/过期路径
- [x] T045 [US2] 在 `services/api-service/app/rate_limit.py` 实现 Redis 固定窗口限流器（IP 每次尝试计数；phone_normalized 仅在规范化成功后）、统一 `RATE_LIMITED` 结果、Redis 错误 fail-closed
- [x] T046 [US2] 按 `contracts/business-codes.md` 在 `services/api-service/app/api/v1/auth.py` 接线限流 + 错误码 HTTP 映射（`400/409/429/503/500`）
- [x] T047 [P] [US2] 在 `services/api-service/app/domain/users/privacy.py` 与 `services/api-service/app/observability.py` 实现手机号脱敏辅助并确保注册路径日志脱敏
- [x] T048 [US2] 在 `frontend/src/pages/Register.tsx` 与 `frontend/src/api/v1/auth.ts` 将 API 错误码映射为中文 UI 文案（字段级 + 表单级），失败时保留输入
- [x] T049 [US2] 在 `frontend/src/pages/Register.tsx` 确保进行中提交按钮忙碌/禁用；超时/网络失败显示错误（非成功）；**手动** 重试在会话内复用同一幂等键（无自动重试）
- [x] T050 [US2] 重跑 US2 测试套件与隐私/并发/限流门禁至绿

**检查点**: US1 仍可用；US2 安全属性在 API 与 UI 成立。

---

## Phase 5: User Story 3 - 初始应用界面骨架可导航 (Priority: P2)

**目标**: 在 **US1 最小导航之上** 完成壳层：NotFound/未开放 catch-all、键盘可访问表单语义、窄视口布局、开发者 README。Home/`/register` 已由 US1 存在——扩展，不重建。

**独立测试**: 未知路径显示友好占位与首页/注册链接；仅键盘可完成主表单交互；窄视口提交可见且无横向滚动；`/` 与 `/register` 仍可用（US1 回归）。

### User Story 3 的测试（先写并观察到失败）

- [x] T051 [P] [US3] 在 `frontend/src/App.test.tsx` 添加 `/`、`/register` 与未知路径渲染 NotFound/占位的路由测试
- [x] T052 [P] [US3] 在 `frontend/src/pages/Register.test.tsx` 添加无障碍向测试：带标签输入、错误关联、键盘提交路径
- [x] T053 [P] [US3] 在 `frontend/src/layouts/AppShell.test.tsx` 添加布局/导航回归测试，确保壳层在首页与注册页保留

### User Story 3 的实现

- [x] T054 [P] [US3] 在 `frontend/src/pages/NotFound.tsx` 实现 NotFound / “暂未开放” 页，含回首页与注册链接
- [x] T055 [US3] 在 `frontend/src/App.tsx` 注册 catch-all 路由 `*`，并确保壳层包裹全部页面
- [x] T056 [P] [US3] 在 `frontend/src/pages/Register.tsx` 细化语义化表单标记（`label htmlFor`、`aria-invalid`、错误的 `aria-describedby`）
- [x] T057 [P] [US3] 在 `frontend/src/styles/globals.css` 打磨最小响应式 CSS，使窄视口下提交可见且无横向滚动
- [x] T058 [US3] 更新 `frontend/README.md`：本地运行说明（API 基址、路由）与 **手工 ER-004 检查**：冷启动 dev server，典型机器上 `/register` 3s 内可交互（非 CI 门禁）
- [x] T059 [US3] 重跑 frontend 测试套件至绿

**检查点**: 三条可演示路由 + 注册表单无障碍基线。

---

## Phase 6: Polish 与横切关注点

**目的**: 可追溯性、性能抽查、文档与完整 quickstart。

- [x] T060 [P] 在 `services/api-service/README.md` 文档化迁移 apply/backout 与注册回滚说明
- [x] T060a [P] 在 `services/api-service/README.md` 说明 `users` 与 `registration_idempotency_records` 继承 API Service PostgreSQL 平台备份/恢复（无特性级备份作业；软删除 ≠ restore；幂等为 24h 辅助），并交叉链接 `ops/` 下既有 PG 备份 runbook（若有）
- [x] T061 [P] 在 `ops/runbooks/` 新增或更新受信客户端 IP / `X-Forwarded-For` 限流假设的运维说明（短 runbook 或章节），不含生产密钥
- [x] T061a [P] 在 `ops/runbooks/registration.md`（或 `ops/runbooks/` 下等价路径）编写注册失败模式 runbook（信号、severity、owner=API Service、5xx/503 分诊/恢复、Redis 限流宕机、冲突/限流洪水），无密钥或完整手机号
- [x] T061b [P] 在 `ops/` 下添加注册 Prometheus 告警规则定义（5xx/`SERVICE_UNAVAILABLE` 升高、限流后端不可用、异常失败率；例如 `ops/alerts/registration.yml` 或项目标准告警路径），接线 `services/api-service/app/observability.py` 指标
- [x] T061c [P] 在 `ops/` 或 `shared/tests/` 添加或扩展测试/夹具：校验告警规则文件可解析并引用既有指标名（轻量结构检查）
- [x] T062 从仓库根运行完整 `make lint` 与 `make test`；修复触及组件的回归
- [x] T063 [P] 在 `services/api-service/tests/integration/test_register_performance.py` 添加注册 p95 延迟断言或文档化本地集成微基准（或以 skip-unless-env 标记并附 CI 指引）
- [x] T064 执行 `specs/003-user-registration-ui/quickstart.md` 手工路径，含 **§6 首屏 ≤3s**（`/register`），并在测试/文档中记录缺口修复
- [x] T065 核实未引入 Gateway/Billing/Admin 注册耦合（grep/评审），并保持这些树不变
- [x] T066 确认域包覆盖率 ≥80%，SC-005 脱敏扫描测试保持绿色

---

## 依赖与执行顺序

### 阶段依赖

- **Phase 1 (Setup)**: 无依赖 — 可立即开始
- **Phase 2 (Foundational)**: 依赖 Setup — **阻塞全部用户故事**
- **Phase 3 (US1)**: 依赖 Foundational — MVP
- **Phase 4 (US2)**: 依赖 Foundational；建立在 US1 service/router/UI 上（逻辑上在 US1 之后以减少 thrash）
- **Phase 5 (US3)**: 依赖 Foundational；可与晚期 US1 部分重叠（壳层已在 T032–T035 启动），但 NotFound/无障碍在 US1 路由存在后完成
- **Phase 6 (Polish)**: 依赖 US1–US3 期望范围完成

### 用户故事依赖

| 故事 | 优先级 | 依赖 | 可独立测试？ |
|------|--------|------|--------------|
| US1 | P1 | Phase 2 | 是 — 成功路径 API+UI |
| US2 | P1 | Phase 2（+ 优先 US1 代码） | 是 — 滥用/负向矩阵 |
| US3 | P2 | Phase 2（+ 优先 US1 壳层） | 是 — 若 mock 后端则路由/无障碍 |

### 每个故事内部

1. 写测试 → 观察到失败
2. 实现 models/services/endpoints 或 UI
3. 使测试通过
4. 进入下一故事前检查点

### 并行机会

- T001–T007（T003 锁文件顺序有争议时除外）：锁规划后可并行 T001/T002/T004–T007
- T008–T010 foundational 测试可并行
- T020–T025 US1 测试可并行
- T037–T043 US2 测试可并行
- T051–T053 US3 测试可并行
- 若共享契约夹具，Frontend（T031–T035）可在 API（T026–T030）落地时对 mock API 推进

---

## 并行示例：User Story 1

```bash
# After Phase 2 complete, launch US1 tests in parallel:
# T020 services/api-service/tests/unit/test_registration_validation.py
# T021 services/api-service/tests/unit/test_registration_service.py
# T022 services/api-service/tests/integration/test_register_api.py
# T023 services/api-service/tests/unit/test_registration_privacy.py
# T024 frontend/src/pages/Register.test.tsx (+ auth.test.ts)
# T025 frontend/src/App.test.tsx

# Then implementation streams:
# API: T026 → T027 → T028 → T029 → T030
# FE:  T031 → T032 → T033 → T034 → T035 (can parallel API after contract stable)
```

---

## 并行示例：User Story 2

```bash
# Tests in parallel: T037–T043
# Implementation: T044–T046 sequential on service/router; T047 [P]; T048–T049 UI; T050 verify
```

---

## 实施策略

### MVP 优先（仅 User Story 1）

1. 完成 Phase 1 Setup
2. 完成 Phase 2 Foundational
3. 完成 Phase 3 US1
4. **停止并验证** US1 独立测试 / quickstart 成功路径
5. 演示无令牌的端到端注册

### 增量交付

1. Setup + Foundational → 基础就绪
2. US1 → MVP 演示
3. US2 → 生产安全的注册语义
4. US3 → 壳层/无障碍完整
5. Polish → CI 绿 + quickstart

### 建议人员分工

- Dev A: API Phase 2–4
- Dev B: Frontend Phase 1/3–5（契约就绪后）
- 同步 OpenAPI 字段名与业务码

---

## 备注

- **不要** 实现 SF04 登录/令牌、密码、SMS 或 Gateway 注册代理
- 软删除后再注册必须用 `ACCOUNT_UNAVAILABLE`，不得静默重建
- Redis 宕机 ⇒ 注册 fail-closed（503），禁止无限写入
- 每任务或逻辑组提交；保持 Conventional Commits
- 可在任意检查点停下独立验证故事
- 格式校验：每任务使用 `- [ ]`、`Tnnn`、可选 `[P]`、故事标签仅在 US 阶段，以及精确文件路径

---

## 任务计数摘要

| 阶段 | 任务数 | ID |
|------|--------|-----|
| Phase 1 Setup | 7 | T001–T007 |
| Phase 2 Foundational | 12 | T008–T019 |
| Phase 3 US1 | 17 | T020–T036 |
| Phase 4 US2 | 14 | T037–T050 |
| Phase 5 US3 | 9 | T051–T059 |
| Phase 6 Polish | 11 | T060–T066（+ T060a, T061a–c） |
| **合计** | **70** | T001–T066（+ T060a, T061a–c） |

| 用户故事 | 任务数（带故事标签） |
|----------|----------------------|
| US1 | 17 |
| US2 | 14 |
| US3 | 9 |

---

## Phase 7: 收敛

**目的**: 弥合已标完成任务与当前代码库的差距（评估日期 2026-07-23）。先前实施已交付核心 handlers/UI，但宪章要求的测试、覆盖率及若干 US2/US3 验收证据仍不完整。

**评估摘要**: 域 `service.py` 单元覆盖约 39%；缺少并发、软删除冲突、幂等过期、迁移回退、HTTP 防枚举限流或前端错误码映射的自动化证明。集成成功路径仅环境门控。

- [x] T067 在 `services/api-service/tests/integration/test_users_migration.py` 为 `users` 与 `registration_idempotency_records` 添加 Alembic upgrade/downgrade 测试，对齐 FR-005 / 宪章 III / plan:migration（缺失）
- [x] T068 在 `services/api-service/tests/unit/test_registration_service.py` 和/或 `services/api-service/tests/integration/test_register_idempotency.py` / `test_register_conflicts.py` 添加 RegistrationService 测试：成功路径、校验错误、`PHONE_ALREADY_REGISTERED`、`ACCOUNT_UNAVAILABLE`（软删除夹具）、幂等重放、同键异体、24h 过期键，对齐 FR-004–007a / SC-001 / SC-003 / US2（缺失）
- [x] T069 在 `services/api-service/tests/integration/test_register_concurrency.py` 添加并发测试：100 并行同规范化号注册最多一条 `users` 行，对齐 FR-008 / SC-002（缺失）
- [x] T070 在 `services/api-service/tests/integration/test_register_rate_limit.py` 添加 HTTP/集成限流测试：默认 IP 20/15m 与 phone 5/15m、Redis 不可用 fail-closed 503、防枚举（占用/软删/未知/非法计数规则下 `RATE_LIMITED` 形状一致），对齐 FR-018–020a / SC-009 / ER-002（缺失）
- [x] T071 在 `services/api-service/tests/integration/test_register_failures.py` 添加 DB 不可用 / 事务回滚测试，证明无部分用户行，对齐 ER-005 / 失败场景 1（缺失）
- [x] T072 将变更域包（`app/domain/users/`、注册路径）含 `service.py` 与 `auth.py` 分支的行覆盖率提升并门禁 ≥80%；在 `services/api-service/` 文档化或修复 CI 覆盖率调用，对齐宪章 V / T066（部分）
- [x] T073 在 `frontend/src/pages/Register.test.tsx`（mock API）添加前端测试：占用 vs 软删不可用 vs 限流表单错误、忙碌/禁用提交、request_id 展示，对齐 SC-007 / US2 / FR-013–014 / FR-020（部分）
- [x] T074 在 `frontend/src/layouts/AppShell.test.tsx` 添加布局/导航回归测试，对齐 US3 / T053（缺失）
- [x] T075 在 `ops/runbooks/registration.md`（或 `ops/runbooks/` 下专用说明）文档化受信客户端 IP / `X-Forwarded-For` 注册限流假设，对齐 plan:security / T061（缺失）
- [x] T076 确保依赖不可用时的注册响应使用统一业务包络（`code`/`message`/`request_id`/`timestamp`），而非裸 FastAPI `detail`，涉及 `services/api-service/app/dependencies.py` 与 `services/api-service/app/api/v1/auth.py`，对齐 FR-009（部分）
- [x] T077 在 `services/api-service/tests/integration/test_register_performance.py` 添加环境门控或文档化的注册 p95 延迟微基准，对齐 SC-004 / ER-004 / T063（缺失）
- [x] T078 在 `services/api-service/tests/unit/test_registration_privacy.py`（和/或集成）添加自动化日志/响应脱敏扫描（或加强隐私测试），确保完整合成手机号不得出现在注册日志字段或错误体，对齐 SC-005 / FR-011（部分）
