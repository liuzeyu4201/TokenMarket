# Implementation Plan: V0.2 契约与端点目录治理

**Branch**: `020-endpoint-catalog-governance` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/020-endpoint-catalog-governance/spec.md`

## Summary

建立 TokenMarket V0.2 的**唯一发布范围事实源**：冻结日 2026-08-31 的 OpenAI /
Anthropic / Google Vertex Endpoint Catalog，以及 Project、Provider Connection、
route decision、usage、pricing、ledger、audit 的版本化 HTTP/事件契约。Gateway 与
三个 Python 服务在启动时校验目录主版本并失败关闭；数据面准入由纯函数判定
`ENDPOINT_NOT_CATALOGED` / `CONTROL_PLANE_NOT_ALLOWED` / `PREVIEW_NOT_ENABLED` /
`DEDICATED_PROJECT_REQUIRED`。本功能**不**转发上游、**不**实现领域 CRUD、**不**
引入 new-api。

技术路径见 [research.md](./research.md)。

## Technical Context

**Language/Version**: Go 1.25.14（proxy-gateway）；Python 3.11.15（api/billing/admin
与 `tests/workflow`）；契约为 JSON Schema 2020-12 与 OpenAPI 3.0.3。

**Primary Dependencies**: Go 标准库 `encoding/json`；Python 标准库 `json` /
`pathlib`。不新增 jsonschema 运行时依赖；完整性由领域校验器实现。不引入
new-api、厂商官方 SDK 或跨协议转换库。

**Storage**: 已提交的版本化契约文件（git 为发布事实源）。**无数据库迁移**。

**Testing**: Go `testing` + `-race`（`endpcatalog` 包 ≥80% 行覆盖）；pytest 契约/
负向/生成确定性；workflow 测试更新共享契约总表。禁止真实厂商网络。

**Target Platform**: 本地主机进程与 CI；目录加载不访问网络。

**Project Type**: monorepo 共享契约 + 多服务启动门禁。

**Performance Goals**: 全量冻结目录加载 + 单次判定 p95 < 5 ms（本机单元，CI 不对
墙钟 fail，但对正确性 fail）。

**Constraints**: 同协议透传范围仅登记、不转换；控制面拒绝；测试额度契约禁止
充值/提现/法币锚定形状；凭据契约禁止明文回读；Volcano V0.1 契约保留且独立。

**Scale/Scope**: 三厂商冻结日稳定数据面全量枚举 + 控制面/preview 样本；7 个领域
契约族；4 个运行时消费者的主版本门禁。

### Affected Components

| Component | Owner / Planned change | Explicit non-change |
|-----------|------------------------|---------------------|
| `shared/contracts/endpoint-catalog/v1/` | 物化本目录 `contracts/` 中的 schema、catalog、生成清单、冻结记录 | 不修改 volcano-* 契约语义 |
| `shared/contracts/{project,provider-connection,route-decision,usage,pricing,ledger,audit}/v1/` | 新版本化契约 | 领域服务暂不实现写入 |
| `shared/contracts/README.md` 与 `tests/workflow/test_contracts.py` | 登记新契约，修复既有磁盘/总表漂移 | 不削弱既有 SF02 字节等同断言 |
| `services/proxy-gateway/internal/domain/endpcatalog/` | 加载、校验、匹配、准入判定、启动失败关闭 | 不替换现有 volcano 代理路径 |
| `services/{api,billing,admin}-service/app/` | 启动时校验目录主版本 | 不新增 Project HTTP 在本 SF |
| `docs/decisions/005-endpoint-catalog-governance.md` | 新 ADR | — |
| `ops/runbooks/endpoint-catalog.md` | 加载失败与目录变更 | 不新增公开 Make 动作 |
| `frontend/` | 无 | — |

**Contracts**: 设计源位于本功能 `contracts/`，实现时物化到 `shared/contracts/`。

**Data & Migrations**: 见 [data-model.md](./data-model.md)。无 Alembic 变更。

**Security & Privacy**: 控制面路径登记为 `control_plane`；夹具仅合成数据；
Provider Connection 契约无明文读回；日志只记录目录版本与错误码。

**Observability & Reliability**: 启动日志：`catalog_major`、`catalog_minor`、
`freeze_date`、`record_count`、结果码。失败码 `CATALOG_LOAD_FAILED` /
`CATALOG_VERSION_MISMATCH`。Gateway readiness 在目录未锁定时不得 ready；
liveness 不因目录问题以外的 upstream 失败而失败（本 SF 不改变 upstream 探针）。

**Deployment & Rollback**: 契约与加载器随镜像发布。回滚=回退 git/镜像到上一兼容
主版本目录。主版本不兼容包必须失败关闭。

## Constitution Check

*GATE: MUST pass before Phase 0 research and MUST be re-checked after Phase 1 design.*

### Pre-Research Gate

| Gate | Result | Planned evidence |
|------|--------|------------------|
| Architecture and ownership | PASS | 契约归 `shared/contracts`；判定归 gateway 领域包；Python 服务只做主版本门禁；新共享抽象有 ADR 005 |
| Contracts and compatibility | PASS | schema/OpenAPI/事件在实现前定义；兼容策略只增补 |
| Security and privacy | PASS | 控制面拒绝；无密钥；无明文回读形状 |
| Data correctness | PASS | 唯一键；金额定点/整数；账本不可变形状 |
| Testing | PASS | 先测试后实现；负向夹具；确定性生成 |
| Operations | PASS | 启动日志、失败码、runbook |
| Delivery | PASS | 无新公开 Make；走既有 `make test`/`make ci` |
| Documentation language | PASS | 规格/计划/任务/ADR/runbook 简体中文 |

### Post-Design Gate

| Gate | Result | Evidence |
|------|--------|----------|
| Architecture and ownership | PASS | research D1–D3；无跨服务读库；无新微服务 |
| Contracts and compatibility | PASS | `contracts/` 已定义 catalog + 7 领域契约 + 错误码 |
| Security and privacy | PASS | control_plane 记录与错误码；凭据契约 `write_only` |
| Data correctness | PASS | data-model 唯一键与账本追加 |
| Testing | PASS | quickstart 列出可运行命令 |
| Operations | PASS | 失败关闭与 runbook 路径 |
| Delivery | PASS | 物化 + 字节等同测试 |
| Documentation language | PASS | 中文设计文档 |

Any failed gate MUST block implementation. 本计划无豁免。

## Project Structure

### Documentation (this feature)

```text
specs/020-endpoint-catalog-governance/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
├── checklists/requirements.md
├── evidence/
└── tasks.md
```

### Source Code (repository root)

```text
shared/contracts/endpoint-catalog/v1/
shared/contracts/project/v1/
shared/contracts/provider-connection/v1/
shared/contracts/route-decision/v1/
shared/contracts/usage/v1/
shared/contracts/pricing/v1/
shared/contracts/ledger/v1/
shared/contracts/audit/v1/
services/proxy-gateway/internal/domain/endpcatalog/
services/api-service/app/domain/endpcatalog/
services/billing-service/app/domain/endpcatalog/
services/admin-service/app/domain/endpcatalog/
tests/workflow/test_endpoint_catalog.py
docs/decisions/005-endpoint-catalog-governance.md
ops/runbooks/endpoint-catalog.md
```

**Structure Decision**: 契约源在本功能 `contracts/`，物化到 `shared/contracts`
（与 SF02 字节等同模式一致）。运行时判定只放在 Go 领域包；Python 三服务仅加载
版本门禁，避免三套判定逻辑。生成人类清单的函数与测试放在 `tests/workflow`，
输入仅 `catalog.json`。

## Complexity Tracking

无宪章违规，本表为空。
