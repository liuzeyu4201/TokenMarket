---
description: "Task list for V0.2 契约与端点目录治理"
---

# Tasks: V0.2 契约与端点目录治理

**Input**: Design documents from `/specs/020-endpoint-catalog-governance/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Language**: 任务描述默认简体中文。标识符与路径保持原样。

**Tests**: 行为变更必须先写测试。

**Organization**: 按用户故事分阶段，先测试后实现。

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: 功能目录、ADR、契约源就位

- [x] T001 确认 `specs/020-endpoint-catalog-governance/` 含 spec/plan/research/data-model/quickstart/contracts
- [x] T002 新增 ADR `docs/decisions/005-endpoint-catalog-governance.md` 并在 `docs/decisions/README.md` 登记
- [x] T003 新增运行手册 `ops/runbooks/endpoint-catalog.md`（加载失败、版本不匹配、目录变更门禁）

---

## Phase 2: Foundational

**Purpose**: 物化契约骨架与测试入口，阻塞所有故事

- [x] T004 将 `specs/020-endpoint-catalog-governance/contracts/*.schema.json`、`*.openapi.yaml`、`*.md` 物化到 `shared/contracts/{endpoint-catalog,project,provider-connection,route-decision,usage,pricing,ledger,audit}/v1/`（catalog.json/CATALOG.md 稍后由 US1 生成）
- [x] T005 更新 `shared/contracts/README.md` 总表，加入全部新契约与兼容说明
- [x] T006 更新 `tests/workflow/test_contracts.py` 的 `EXPECTED_CATALOG`，使磁盘目录与总表一致（含既有 volcano/role 契约若在磁盘上）
- [x] T007 [P] 在 `services/proxy-gateway/internal/domain/endpcatalog/` 创建包骨架（空类型即可）
- [x] T008 [P] 在 `services/api-service/app/domain/endpcatalog/`、`services/billing-service/app/domain/endpcatalog/`、`services/admin-service/app/domain/endpcatalog/` 创建 Python 加载模块骨架

---

## Phase 3: User Story 1 — 冻结日目录可枚举 (P1)

**Goal**: 三厂商冻结日稳定数据面唯一记录

**Independent Test**: `pytest tests/workflow/test_endpoint_catalog.py` 覆盖唯一键与家族覆盖

- [x] T009 [US1] 先写 `tests/workflow/test_endpoint_catalog.py`：唯一键、三厂商家族覆盖、缺字段拒绝、重复键拒绝
- [x] T010 [US1] 先写 `services/proxy-gateway/internal/domain/endpcatalog/validate_test.go`：完整性与唯一键
- [x] T011 [US1] 实现目录记录生成源与 `catalog.json`（冻结日 2026-08-31 全量枚举）于 `shared/contracts/endpoint-catalog/v1/catalog.json` 及评审源副本
- [x] T012 [US1] 实现 Go 校验器 `services/proxy-gateway/internal/domain/endpcatalog/validate.go` 与加载 `load.go`
- [x] T013 [US1] 实现 Python 完整性校验供 workflow 测试调用 `tests/workflow/endpoint_catalog_lib.py`

---

## Phase 4: User Story 2 — schema 拒绝不完整记录 (P1)

**Goal**: 缺稳定性/状态性/传输/计量/夹具必失败

**Independent Test**: 负向夹具 100% 被拒

- [x] T014 [US2] 先写负向夹具测试（缺 stability/stateful/transport/metering_source/test_fixture_version、非法枚举、原地语义变更检测）于 `tests/workflow/test_endpoint_catalog.py` 与 `validate_test.go`
- [x] T015 [US2] 实现对应拒绝分支；preview/beta 必须 `requires_project_opt_in=true`

---

## Phase 5: User Story 3 — 准入判定 (P1)

**Goal**: stable/preview/control-plane/unknown/stateful 行为

**Independent Test**: Go 表驱动 `admit_test.go`

- [x] T016 [US3] 先写 `services/proxy-gateway/internal/domain/endpcatalog/admit_test.go` 覆盖 FR-005–FR-008 全部错误码
- [x] T017 [US3] 实现 `admit.go` 最长模板匹配与 `CatalogAdmissionDecision`；附带 `admit_bench_test.go` 记录全量目录判定（CI 不对 5ms 墙钟失败，但对正确性失败）
- [x] T018 [US3] 先写不变量测试：跨协议转换入口不存在、new-api 不在契约总表、凭据明文读回字段不存在、未确定费用不得用 0 表示（契约静态断言）于 `tests/workflow/test_v02_invariants.py`
- [x] T019 [US3] 实现/巩固契约静态断言使 T018 通过

---

## Phase 6: User Story 4 — 主版本失败关闭 (P1)

**Goal**: 四消费者启动校验 catalog_major

**Independent Test**: 不兼容主版本加载失败

- [x] T020 [US4] 先写 `version_test.go` 与三服务 `tests/unit/test_endpcatalog.py`
- [x] T021 [US4] 实现 Go `MustLoad` 与环境变量 `TOKENMARKET_CATALOG_MAJOR`（缺省等于已发布主版本）
- [x] T022 [US4] 将加载接入 `services/proxy-gateway/cmd/gateway/main.go`：失败则 `os.Exit(1)`；成功必须记录 `catalog_major`/`catalog_minor`/`freeze_date`/`record_count`（无敏感字段）；readiness 在未锁定目录时不可 ready
- [x] T023 [P] [US4] 将加载接入 `services/api-service/app/main.py`、`services/billing-service/app/main.py`、`services/admin-service/app/main.py` 启动路径

---

## Phase 7: User Story 5 — 领域契约唯一事实源 (P2)

**Goal**: 七类契约可解析且登记

**Independent Test**: OpenAPI/JSON Schema 解析 + README 总表

- [x] T024 [US5] 先写契约解析测试：Project 无 PATCH mode；Connection 无明文读回；ledger 无 update/delete；usage 含 unresolved；route self_trade_excluded const true
- [x] T025 [US5] 补齐契约文件使 T024 通过（若物化遗漏）

---

## Phase 8: User Story 6 — 确定性人类清单 (P2)

**Goal**: CATALOG.md 同源可重复生成

**Independent Test**: 二次生成字节相同

- [x] T026 [US6] 先写生成器测试 `tests/workflow/test_endpoint_catalog.py::test_catalog_markdown_deterministic`
- [x] T027 [US6] 实现生成器并提交 `shared/contracts/endpoint-catalog/v1/CATALOG.md` 及 specs 源副本
- [x] T028 [US6] 提交/更新 `freeze-record.md` 与兼容说明

---

## Phase 9: Polish

- [x] T029 将物化文件与 `specs/020-endpoint-catalog-governance/contracts/` 做字节等同测试（对齐 SF02 模式）
- [x] T030 运行 gateway `go test ./internal/domain/endpcatalog/ -race` 与相关 pytest；保存日志到 `specs/020-endpoint-catalog-governance/evidence/`
- [x] T031 [P] 更新 `ops/tests/test_ops_assets.py` 如需要识别新 runbook
- [x] T032 确认 `make fmt` 适用路径干净；不降低覆盖率阈值

---

## Dependencies

- Setup → Foundational → US1 → US2 → US3 → US4；US5/US6 可在 Foundational 后与 US1 并行，但不共享未完成的 catalog.json。
- US3 依赖 US1 的真实 catalog 记录（至少各标签一条）。

## Parallel examples

- T007/T008 骨架可并行
- T023 三个 Python 服务接入可并行
- T031 与 T030 可并行

## Implementation strategy

先 US1+US2 得到可校验目录，再 US3 判定，再 US4 启动门禁，最后清单与领域契约测试。MVP=US1–US4。
