# 任务：角色授权与自买自卖隔离

**输入**: 设计文档来自 `/specs/005-role-access-isolation/`

**前置**: `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`

**语言**: 任务描述与备注默认简体中文；标识符、路径、API 字段、业务码、环境变量保持原文。

**测试**: 每次行为变更均 **必须** 先写测试并在实现前观察到失败。`services/api-service/app/domain/authorization/` 与授权路由要求 ≥80% 行覆盖率；拒绝、自买自卖、失败关闭、IDOR 统一 404、**审计先落盘否则 503**、**会话撤销 401** 分支须直接断言。

**组织**: 按用户故事分组。Setup + Foundational 阻塞全部故事。

| 故事 | 优先级 | MVP? | 内容 |
|------|--------|------|------|
| US1 | P1 | **是** | 默认拒绝角色矩阵 + 所有权 + 会话身份/撤销 + evaluate/夹具 HTTP |
| US2 | P1 | 建议同批 | 路由候选自买自卖排除（纯函数 + HTTP） |
| US3 | P2 | 其后 | 强制脱敏审计：先意图后拒绝，失败 503 |

**MVP 范围**: Phase 1–3（US1）。生产可部署授权边界建议 **US1+US2+US3**。

**明确不在任务内**: 批量授权 API（FR-011）、授权加速层、完整 Key 产品、Gateway 热路径、前端。

## 格式：`[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件，同批次无未完成依赖）
- **[Story]**: `[US1]` / `[US2]` / `[US3]` 仅用于故事阶段
- 每个任务须包含精确文件路径

## 路径约定

- API: `services/api-service/`
- 特性契约源: `specs/005-role-access-isolation/contracts/`
- 共享契约（实现时）: `shared/contracts/role-access-isolation/v1/`
- 测试: `services/api-service/tests/{unit,contract,integration}/`

---

## Phase 1: Setup（共享基础设施）

**目的**: 提升契约、包骨架、配置占位；尚无授权业务行为。

- [x] T001 将特性契约提升至 `shared/contracts/role-access-isolation/v1/`：复制 `specs/005-role-access-isolation/contracts/role-access-isolation.openapi.yaml`、`business-codes.md`、`authorization-matrix.md`，并在 `shared/contracts/README.md`（或等价索引）登记所有权/版本
- [x] T002 [P] 在 `docs/api/README.md`（若存在）或 `services/api-service/README.md` 增加 role-access-isolation v1 契约索引链接
- [x] T003 [P] 创建授权包骨架（仅 `__init__.py` / 空模块）：`services/api-service/app/domain/authorization/`、`services/api-service/app/repositories/authorization.py` 占位、`services/api-service/app/schemas/authorization.py` 占位、`services/api-service/app/api/v1/authorization.py` 占位
- [x] T004 [P] 在 `services/api-service/tests/contract/test_role_access_contract_assets.py`（或 `shared/tests/` 等价路径）添加契约资产存在/OpenAPI 可解析冒烟测试
- [x] T005 [P] 在 `.env.example` 文档化 `AUTHORIZATION_FIXTURES_ENABLED`（默认 false）与 `APP_ENV` 约束说明，无真实密钥

**检查点**: 契约可发现；空包存在；无授权行为。

---

## Phase 2: Foundational（阻塞性前置）

**目的**: 迁移、模型、策略版本常量、会话身份依赖钩子、测试工厂；阻塞全部用户故事。

**关键**: 本阶段完成前不得开始 US1–US3 实现。先写 foundational 测试并观察到失败。

- [x] T006 [P] 在 `services/api-service/tests/integration/test_authorization_migration.py` 添加失败测试：upgrade 创建 `resource_ownerships`、`authorization_security_events`、`authorization_audit_outbox` 及约束/索引；downgrade 可回退
- [x] T007 [P] 在 `services/api-service/tests/unit/test_authorization_matrix_table.py` 添加失败测试：按 `shared/contracts/role-access-isolation/v1/authorization-matrix.md` 断言 `authz-matrix-v1` 全部角色×动作 allow/deny 表
- [x] T008 [P] 在 `services/api-service/tests/unit/test_authorization_decision_codes.py` 添加失败测试：内部 `reason_code` → 对外业务码/HTTP 映射对齐 `business-codes.md`（含 401/403/404/503）
- [x] T009 编写 Alembic 修订 `services/api-service/alembic/versions/0004_role_access_isolation.py`（接在 `0003_phone_login_session` 之后）：三表 + UNIQUE/CHECK/索引/FK，直至 T006 通过
- [x] T010 在 `services/api-service/app/domain/authorization/models.py` 实现 SQLAlchemy 模型 `ResourceOwnership`、`AuthorizationSecurityEvent`、`AuthorizationAuditOutbox`，对齐 `data-model.md`（含 `disabled` 生命周期）
- [x] T011 在 `services/api-service/app/domain/authorization/matrix.py` 实现 `POLICY_VERSION = "authz-matrix-v1"`、动作枚举与默认拒绝矩阵查询 API，直至 T007 通过
- [x] T012 在 `services/api-service/app/domain/authorization/codes.py`（或 `app/errors.py` 扩展）实现稳定业务码与 HTTP 映射，直至 T008 通过
- [x] T013 在 `services/api-service/app/repositories/authorization.py` 实现 ownership / events / outbox 基础仓储方法（create、get_by_type_id、list_by_owner、insert_event、insert_outbox）
- [x] T014 在 `services/api-service/app/dependencies.py`（复用 SF04 会话校验）暴露「仅返回已认证 `user_id`+`session_id`」依赖；会话缺失/过期/**已撤销** → 未认证；注释明确 **不得** 用 `role_snapshot` 作权限
- [x] T015 在 `services/api-service/tests/integration/conftest_authorization.py`（或扩展既有 conftest）提供：可丢弃 PG、合成 buyer/seller/both 用户工厂、会话 Cookie 工厂、**撤销会话辅助**、ownership 行工厂
- [x] T016 [P] 在 `services/api-service/app/observability.py` 增加授权指标钩子桩：`action`/`result`/`reason_code` 计数与耗时直方图（无 PII/密钥标签）

**检查点**: 迁移可应用/回滚；矩阵与码表已单测；仓储/身份依赖/测试工厂就绪。

---

## Phase 3: User Story 1 - 按角色使用允许的能力 (Priority: P1) 🎯 MVP

**目标**: 已认证用户仅能执行角色矩阵允许的声明动作；身份仅来自会话；所有权与账户状态在服务端强制；会话撤销不得进入允许路径；提供 evaluate + 非生产夹具 HTTP。

**独立测试**: buyer/seller/both 矩阵；伪造身份无效；跨用户统一 404；**撤销会话后 evaluate → 401**；夹具生产关闭。

### User Story 1 的测试（先写并观察到失败）

- [x] T017 [P] [US1] 在 `services/api-service/tests/unit/test_authorization_service_role.py` 添加单元测试：三类角色 × 声明动作矩阵 + 账户 suspended/deleted/非 active 拒绝（mock 用户加载）
- [x] T018 [P] [US1] 在 `services/api-service/tests/unit/test_authorization_service_ownership.py` 添加单元测试：非所有者/soft_deleted/缺失 → 统一 not_found；创建 owner=self；**revoke → disabled**
- [x] T019 [P] [US1] 在 `services/api-service/tests/unit/test_authorization_ignore_client_identity.py` 添加单元测试：请求中的 `user_id`/`role`/`owner_user_id` 被忽略
- [x] T020 [P] [US1] 在 `services/api-service/tests/contract/test_authorization_openapi.py` 添加契约测试：evaluate/fixtures 路径与包络字段对齐 OpenAPI
- [x] T021 [P] [US1] 在 `services/api-service/tests/integration/test_authorization_evaluate_api.py` 添加集成测试：真实 PG + 会话；buyer/seller/both 矩阵抽样 HTTP；**会话撤销/缺失后 evaluate → 401 `UNAUTHENTICATED`，允许次数为 0**（SC-006 / FR-006a）
- [x] T022 [P] [US1] 在 `services/api-service/tests/integration/test_authorization_idor.py` 添加负向集成：跨用户读/改 → 404 同码；与随机 UUID 不可区分
- [x] T023 [P] [US1] 在 `services/api-service/tests/integration/test_authorization_fixtures_gate.py` 添加测试：`AUTHORIZATION_FIXTURES_ENABLED=false` 或非 local/test 时夹具不可用
- [x] T024 [P] [US1] 在 `services/api-service/tests/integration/test_authorization_fail_closed.py` 添加测试：DB 不可达时 evaluate → 503 `SERVICE_UNAVAILABLE`，无 allow（SC-004c）
- [x] T025 [P] [US1] 在 `services/api-service/tests/integration/test_authorization_role_live_read.py` 添加测试：会话 `role_snapshot` 与 DB 角色不一致时以 DB 为准（≤1s/立即生效，SC-003）

### User Story 1 的实现

- [x] T026 [P] [US1] 在 `services/api-service/app/schemas/authorization.py` 实现 Evaluate/Fixture 请求响应 DTO，对齐 OpenAPI
- [x] T027 [US1] 在 `services/api-service/app/domain/authorization/service.py` 实现 `AuthorizationService.authorize`：固定顺序（用户事实 → eligible → 矩阵 → 所有权/生命周期）→ `Decision`，直至 T017–T019 通过
- [x] T028 [US1] 在 `services/api-service/app/domain/authorization/service.py`（或 `ownership_service.py`）实现夹具 create/read/update/disable/revoke 写路径：变更前 authorize；owner 仅会话用户；**revoke 置 `disabled`**
- [x] T029 [US1] 在 `services/api-service/app/api/v1/authorization.py` 实现 `POST /api/v1/authorization/evaluate` 与 fixtures 路由；未认证 401；映射 FR-007a/ER-001 状态码
- [x] T030 [US1] 在 `services/api-service/app/main.py` 挂载 authorization 路由；夹具路由受 `AUTHORIZATION_FIXTURES_ENABLED` + `APP_ENV` 门禁
- [x] T031 [US1] 在 `services/api-service/app/config.py`（或既有 settings）增加授权夹具开关校验；生产误开 fail-closed（启动或 readiness）
- [x] T032 [P] [US1] 在 `services/api-service/app/observability.py` 与 `services/api-service/app/domain/authorization/service.py` 接线指标：allow/deny 与 reason
- [x] T033 [US1] 重跑 `services/api-service/tests/unit/test_authorization_*.py` 与 US1 集成测试至绿；确认 `services/api-service/app/domain/authorization/` 覆盖率可统计 ≥80%

**检查点**: MVP — 角色矩阵 + 所有权 + 会话撤销 + evaluate/夹具可独立演示。

---

## Phase 4: User Story 2 - 阻止自买自卖路由 (Priority: P1)

**目标**: 路由候选排除 `owner_user_id == buyer_user_id`；无其他候选时不得降级选本人；所有权变更对新请求立即/≤1s 生效。

**独立测试**: 混合候选不含本人；仅本人 → `NO_ROUTE_CANDIDATE`；1000 次 0 命中（SC-002）。

### User Story 2 的测试（先写并观察到失败）

- [x] T034 [P] [US2] 在 `services/api-service/tests/unit/test_route_exclude_self.py` 添加纯函数单元测试：混合候选、仅本人、空列表、disabled/soft_deleted 不可入选
- [x] T035 [P] [US2] 在 `services/api-service/tests/unit/test_route_exclude_self.py`（或独立文件）添加属性/循环测试：1000 次随机候选含本人 Key 时选中次数为 0（SC-002）
- [x] T036 [P] [US2] 在 `services/api-service/tests/unit/test_authorization_service_route.py` 添加：seller 调用 `route_candidate_exclude_self` → 角色拒绝；buyer/both 允许过滤
- [x] T037 [P] [US2] 在 `services/api-service/tests/integration/test_route_exclude_api.py` 添加 HTTP 集成：`POST /api/v1/authorization/route-candidates/exclude-self` 过滤与空候选 404 `NO_ROUTE_CANDIDATE`
- [x] T038 [P] [US2] 在 `services/api-service/tests/integration/test_ownership_change_visibility.py` 添加：所有权/生命周期变更后新请求立即用新事实（无陈旧本人 Key 入选，SC-003）

### User Story 2 的实现

- [x] T039 [P] [US2] 在 `services/api-service/app/domain/authorization/route_exclude.py` 实现 `exclude_self_owned_seller_keys(buyer_user_id, candidates) -> filtered`，直至 T034–T035 通过
- [x] T040 [US2] 在 `services/api-service/app/domain/authorization/service.py` 将 `route_candidate_exclude_self` 纳入 authorize/专用方法（矩阵 + 过滤 + 空结果决策），直至 T036 通过
- [x] T041 [US2] 在 `services/api-service/app/api/v1/authorization.py` 实现 exclude-self 端点与包络，直至 T037 通过
- [x] T042 [US2] 在 `services/api-service/app/observability.py` 扩展指标：`excluded_count`、空候选结果计数（低基数）
- [x] T043 [US2] 重跑 `services/api-service/tests/unit/test_route_exclude_self.py` 与 US1+US2 集成测试至绿

**检查点**: 自买自卖排除可独立验收。

---

## Phase 5: User Story 3 - 审计敏感授权结果 (Priority: P2)

**目标**: 强制审计可按 `request_id` 查询；**先提交审计意图再返回业务拒绝**；意图失败 → **503**；高频 `use`/路由成功通过不写逐条审计。

**独立测试**: 拒绝与状态变更可查；模拟落盘失败 → 503 非裸 403/404；`proxy_key.use` allow 无 event 行但有指标。

### User Story 3 的测试（先写并观察到失败）

- [x] T044 [P] [US3] 在 `services/api-service/tests/unit/test_authorization_audit_policy.py` 添加单元测试：强制审计 outcome vs `proxy_key.use` allow / 路由成功过滤仅指标（FR-010c）
- [x] T045 [P] [US3] 在 `services/api-service/tests/integration/test_authorization_audit_persist.py` 添加集成：拒绝与 fixture 状态变更后可按 `request_id` 查询 `authorization_security_events`；字段无密钥/完整手机号（SC-005）
- [x] T046 [P] [US3] 在 `services/api-service/tests/integration/test_authorization_audit_fail_closed.py` 添加：审计/outbox **无法在响应前落盘** → **503**，不返回无证据的 403/404；状态变更回滚（FR-010a / SC-004c）
- [x] T047 [P] [US3] 在 `services/api-service/tests/integration/test_authorization_audit_use_path.py` 添加：`proxy_key.use` 允许路径不插入 security event；指标可观察
- [x] T048 [P] [US3] 在 `services/api-service/tests/unit/test_authorization_audit_redaction.py` 添加：safe_metadata / 资源引用脱敏规则

### User Story 3 的实现

- [x] T049 [US3] 在 `services/api-service/app/domain/authorization/audit.py` 实现审计策略与事件构造（`policy_version`、`reason_code`、`delete_after` 默认 90d）
- [x] T050 [US3] 在 `services/api-service/app/domain/authorization/service.py` 接线：强制路径在返回业务拒绝**之前**同事务直写 event 或 pending outbox；失败 → 503/回滚；**意图已提交后**才返回 403/404（FR-010a）
- [x] T051 [P] [US3] 在 `services/api-service/app/domain/authorization/outbox_worker.py`（或 `app/maintenance/` 模块）实现可选 outbox 刷写到 `authorization_security_events`（至少一次；有界 batch）
- [x] T052 [US3] 在 `services/api-service/app/domain/authorization/service.py` 与夹具写路径确保状态变更与审计同事务成功/失败（FR-010b）
- [x] T053 [P] [US3] 扩展 `services/api-service/app/observability.py`：审计写失败计数、outbox pending 年龄（若 worker 启用）
- [x] T054 [US3] 重跑 `services/api-service/tests/integration/test_authorization_audit_*.py` 及 US1–US3 相关测试至绿

**检查点**: 安全审计闭环；无「无证据业务拒绝」。

---

## Phase 6: Polish 与横切关注点

**目的**: 运维、性能抽查（SC-004a）、quickstart、全量门禁。

- [x] T055 [P] 在 `ops/runbooks/authorization.md`（或等价路径）编写授权失败模式 runbook：503 fail-closed、审计意图失败、夹具误开、outbox 积压；owner=API Service；无密钥
- [x] T056 [P] 在 `ops/alerts/` 添加授权相关 Prometheus 规则草图（授权 503 升高、outbox 积压；引用既有指标名）
- [x] T057 [P] 在 `services/api-service/tests/integration/test_authorization_performance.py` 添加 **env 门控** 微基准：直读路径记录 P95 相对 SC-004a（≤50ms 量级）；默认 CI 不硬失败 unless 显式开启；**不**要求实现加速层 SC-004b
- [x] T058 [P] 在 `services/api-service/README.md` 文档化授权迁移、夹具开关、回滚（停路由/关夹具、保留审计表）、FR-010a 503 语义
- [x] T059 对 `services/proxy-gateway/`、`services/billing-service/`、`services/admin-service/`、`frontend/` 做评审/grep，确认无本功能业务耦合
- [x] T060 从仓库根 `Makefile` 运行 `make lint` 与 `make test`（或组件等价目标）；修复触及文件回归
- [x] T061 按 `specs/005-role-access-isolation/quickstart.md` 执行手工/脚本路径，覆盖 SC-001–006 证据并修缺口
- [x] T062 对 `services/api-service/app/domain/authorization/` 确认 ≥80% 行覆盖，且拒绝/自买自卖/失败关闭/审计顺序/会话撤销分支在 `services/api-service/tests/` 有直接测试

---

## 依赖与执行顺序

### 阶段依赖

```text
Phase 1 Setup
    ↓
Phase 2 Foundational  ── blocks all stories
    ↓
Phase 3 US1 (MVP) ──→ Phase 4 US2 ──→ Phase 5 US3 ──→ Phase 6 Polish
```

- **Phase 1**: 无依赖  
- **Phase 2**: 依赖 Phase 1；**阻塞** US1–US3  
- **Phase 3 US1**: 依赖 Phase 2 — MVP  
- **Phase 4 US2**: 依赖 Phase 2；建议 US1 的 service/路由之后  
- **Phase 5 US3**: 依赖 Phase 2；接线 US1/US2 决策出口  
- **Phase 6**: 依赖目标故事完成  

### 用户故事依赖

| 故事 | 优先级 | 依赖 | 可独立测试？ |
|------|--------|------|--------------|
| US1 | P1 | Phase 2 | 是 — 矩阵 + 所有权 + 会话撤销 + evaluate/夹具 |
| US2 | P1 | Phase 2（+ 优先 US1） | 是 — 纯函数 + exclude-self API |
| US3 | P2 | Phase 2（+ US1/US2 决策路径） | 是 — 审计表 / request_id / 503 路径 |

### 每个故事内部

1. 写测试 → 观察到失败  
2. 实现 domain → repository → HTTP  
3. 测试转绿  
4. 检查点后再进入下一故事  

### 并行机会

- Phase 1：T002–T005  
- Phase 2：T006–T008；T011/T012（模型后）  
- US1：T017–T025  
- US2：T034–T038；T039 可在接口稳定后与 US1 末期重叠  
- US3：T044–T048  
- Polish：T055–T058  

---

## 并行示例：User Story 1

```bash
Task: T017 services/api-service/tests/unit/test_authorization_service_role.py
Task: T018 services/api-service/tests/unit/test_authorization_service_ownership.py
Task: T019 services/api-service/tests/unit/test_authorization_ignore_client_identity.py
Task: T020 services/api-service/tests/contract/test_authorization_openapi.py
Task: T021 services/api-service/tests/integration/test_authorization_evaluate_api.py
Task: T022 services/api-service/tests/integration/test_authorization_idor.py
Task: T024 services/api-service/tests/integration/test_authorization_fail_closed.py
```

## 并行示例：User Story 3

```bash
Task: T044 services/api-service/tests/unit/test_authorization_audit_policy.py
Task: T045 services/api-service/tests/integration/test_authorization_audit_persist.py
Task: T046 services/api-service/tests/integration/test_authorization_audit_fail_closed.py
Task: T047 services/api-service/tests/integration/test_authorization_audit_use_path.py
```

---

## 实施策略

### MVP First（仅 US1）

1. Phase 1 + Phase 2  
2. Phase 3 US1（含 SC-006 会话撤销）  
3. **STOP** 验证矩阵与 IDOR  
4. 立即做 US2（P1）与 US3（审计闭环）  

### 建议首次可部署切片

**US1 + US2 + US3**。不可砍：矩阵/fail-closed、自排除、审计先落盘。

### 增量交付

1. Setup + Foundational  
2. US1 → 授权边界 MVP  
3. US2 → 自买自卖隔离  
4. US3 → 审计合规  
5. Polish → quickstart + make test  

---

## 需求可追溯（摘要）

| 规格项 | 任务 |
|--------|------|
| FR-001–004 矩阵 | T007, T011, T017, T027 |
| FR-005/005a 会话身份 + 事实源角色 | T014, T019, T025, T027 |
| FR-006 账户状态 | T017, T027 |
| FR-006a / SC-006 会话撤销 | T014, T015, T021 |
| FR-007/007a 所有权与统一 404 | T018, T022, T027–T029 |
| FR-008 自排除 | T034–T041 |
| FR-009 / SC-003 ≤1s | T025, T038 |
| FR-010a 先意图后拒绝 / 503 | T046, T050 |
| FR-010b 状态变更同事务审计 | T050, T052 |
| FR-010c use 无逐条审计 | T044, T047 |
| FR-011 批量 | **范围外 — 无任务** |
| ER-004 / SC-004a–c | T024, T057（仅 a+c；无加速实现） |
| ER-005 fail-closed | T024, T046 |
| SC-001–002 | T017, T021, T035 |
| SC-005 | T045, T061 |
| revoke→disabled | T018, T028 |

---

## Notes

- [P] = 不同文件且无未完成依赖  
- 先红后绿；禁止用 collection/import 错误冒充红灯  
- 提交建议按任务或逻辑组；Conventional Commits  
- 夹具路由严禁生产默认开启  
- **无**批量授权、**无**加速层、**无** Gateway/前端任务  
- 本清单于 analyze 收口后重生成，覆盖 I1/I2/U1/C1  

---

## Phase 7: Convergence

**目的**: 闭合 `/speckit-implement` 后相对 spec/plan/tasks 仍未满足的验收与集成缺口。  
**来源**: `/speckit-converge` 2026-08-01 代码对照评估。  
**说明**: 本阶段仅追加；不修改既有 T001–T062 勾选状态。

### Findings → 任务

- [x] T063 [P] 在 `services/api-service/tests/integration/conftest_authorization.py` 提供合成 buyer/seller/both 用户、签发 Cookie 会话、**撤销会话**辅助，并注册到 `tests/conftest.py` 的 `pytest_plugins` per T015 / US1 (partial)
- [x] T064 在 `services/api-service/tests/integration/test_authorization_evaluate_api.py` 用真实 PG + Cookie 覆盖：buyer/seller/both 矩阵抽样 HTTP、`evaluate` 成功/403，以及 **会话撤销后 401 `UNAUTHENTICATED` 允许次数为 0** per SC-006 / FR-006a / US1/AC5 (missing)
- [x] T065 [P] 在 `services/api-service/tests/integration/test_authorization_idor.py` 覆盖跨用户读/改 fixture 资源 → 统一 404 `RESOURCE_NOT_FOUND`，与随机 UUID 不可区分 per FR-007a / US1/AC4 (missing)
- [x] T066 [P] 在 `services/api-service/tests/integration/test_authorization_role_live_read.py` 覆盖会话 `role_snapshot` 与 DB 角色不一致时以 DB 为准（变更后新请求立即生效） per FR-005a / FR-009 / SC-003 (missing)
- [x] T067 [P] 在 `services/api-service/tests/integration/test_authorization_fail_closed.py` 覆盖 DB 不可达时 `evaluate` → 503 `SERVICE_UNAVAILABLE`、无 allow per ER-005 / SC-004c (missing)
- [x] T068 在 `services/api-service/tests/integration/test_route_exclude_api.py` 覆盖 `POST /api/v1/authorization/route-candidates/exclude-self`：过滤本人 Key、仅本人 → 404 `NO_ROUTE_CANDIDATE` per FR-008 / US2 (missing)
- [x] T069 [P] 在 `services/api-service/tests/integration/test_ownership_change_visibility.py` 覆盖所有权/生命周期变更后路由候选立即反映新事实 per FR-009 / US2/AC3 (missing)
- [x] T070 在 `services/api-service/tests/integration/test_authorization_audit_persist.py` 覆盖拒绝与 fixture 状态变更后可按 `request_id` 查询 `authorization_security_events`，且无密钥/完整手机号 per FR-010 / SC-005 (missing)
- [x] T071 [P] 在 `services/api-service/tests/integration/test_authorization_audit_use_path.py` 覆盖 `proxy_key.use` 允许路径 **不**插入 security event、指标可观察 per FR-010c (missing)
- [x] T072 [P] 在 `services/api-service/tests/contract/test_authorization_openapi.py` 将 OpenAPI 路径/请求响应字段与 `shared/contracts/role-access-isolation/v1/role-access-isolation.openapi.yaml` 对齐断言（超出资产存在冒烟） per plan:contracts (partial)
- [x] T073 在 `services/api-service/app/dependencies.py` 暴露可复用的「已认证 `user_id`（+ 可选 `session_id`）」依赖，供 authorization 路由使用；**禁止**用 `role_snapshot` 作权限 per FR-005 / FR-005a / plan:dependencies (partial)
- [x] T074 在 fixture 写路径（`POST/PATCH …/fixtures/resources`）挂接 SF04 Origin + session-bound CSRF 校验（与登出写路径一致） per ER-002 / plan:Security (missing)
- [x] T075 授权审计事件写入真实 `session_id`（bootstrap 解析后传入 `AuthorizationService`，不再恒为 `None`） per FR-010 Key Entity Authorization Audit Event (partial)
- [x] T076 在 `services/api-service/app/domain/authorization/service.py` 审计落盘失败时调用 `record_authz_audit_failure()` per ER-006 / plan:Observability (partial)
- [x] T077 [P] 在 `services/api-service/tests/unit/test_authorization_outbox_worker.py` 覆盖 `outbox_worker.publish_pending_batch` 成功刷写与空批 per plan:outbox_worker / coverage ≥80% (missing)
- [x] T078 [P] 在 `services/api-service/tests/integration/test_authorization_performance.py` 增加 env 门控直读 P95 微基准（相对 SC-004a），默认 CI 不硬失败 per SC-004a / ER-004a (missing)
- [x] T079 对 `app/domain/authorization`（含 service 与 outbox_worker）跑覆盖率并确保 **≥80%** 行覆盖，拒绝/自买自卖/失败关闭/审计顺序/会话撤销分支有直接断言 per Constitution V / tasks T062 (partial)
- [x] T080 按 `specs/005-role-access-isolation/quickstart.md` 跑通矩阵/自排除/会话撤销/审计 503 路径并记录证据缺口修复 per SC-001–006 / T061 (partial)

