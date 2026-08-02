# Implementation Plan：火山方舟凭证与额度验证

**Branch**: `006-volcano-key-validation` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)

**Input**: `specs/006-volcano-key-validation/spec.md`

## Summary

在 **proxy-gateway（Go）** 交付火山方舟凭证的无状态内部验证能力：在 3 秒硬截止内
检查认证、模型可见性与（若存在）可信额度，产出稳定 `error_category` 结果，供
SF08 接入与 SF16 健康消费。V0.1 **默认无 Key 作用域官方额度 API**，额度步骤固定为
`quota_unavailable`（禁止填 0）；`success`/`zero_quota` 通过可注入的 `QuotaReader`
端口与契约测试覆盖，待官方额度源就绪后接线。

技术路径见 [research.md](./research.md)：GET `/api/v3/models` 探活、进程内并发闸门
32/1、内部 HTTP + token、结果契约与调用方合并规则分离。

## Technical Context

**Language/Version**: Go 1.25.12（`services/proxy-gateway/`）

**Primary Dependencies**: 标准库 `net/http`、`context`；既有 gateway 脚手架
（`internal/httpserver`、`internal/observability`）。不引入火山官方 SDK（避免额外依赖面）；
不引入 Redis/PostgreSQL 于本功能。

**Storage**: **N/A** — 无持久化、无迁移。

**Testing**: Go `testing` + 表驱动；`net/http/httptest` 上游替身；竞态检测；
domain/adapter ≥80% 行覆盖；分类/脱敏/闸门/取消负向测试。

**Target Platform**: Linux 服务端与本地 macOS/Linux 主机进程（`make start` 中的 gateway）。

**Project Type**: monorepo 网关领域增量 — 内部验证端口 + 可选内部 HTTP

**Performance Goals**:

| 路径 | 目标 | Spec |
|------|------|------|
| 单次验证硬截止 | ≤ 3s（含有界重试） | FR-003 / SC-002 |
| 正常路径完成率 | 95% < 3s | SC-002 |
| 默认并发 | 全局 32 / 单凭证 1 | FR-012a / SC-002a |

**Constraints**: 无状态；无 Key 落盘；无公开卖家 API；仅 `volcano`；额度默认
`quota_unavailable`；临时类不得由本功能写入永久 invalid；内部路由默认关闭。

**Scale/Scope**: 1 平台适配器、1 内部路由、1 版本契约目录、无新微服务、无 DB。

### Affected Components

| Component | Owner / Planned change | Explicit non-change |
|-----------|------------------------|---------------------|
| `services/proxy-gateway/` | domain 验证端口、volcano 适配器、分类器、并发闸门、脱敏、内部 validate 路由、指标、测试 | 不实现 SF08 持久化、不实现代理转发/路由池、不接多平台 |
| `shared/contracts/volcano-key-validation/v1/` | 实现时提升本目录 `contracts/` | 不修改 role-access / phone-auth 契约 |
| `ops/runbooks/`（按需） | 内部验证失败、invalid_response 告警分诊 | 不新增公开 Make 动作 |
| `services/api-service/` | 本功能 **无** 强制接线；SF08 再消费内部 HTTP | 不复制 volcano 协议解析 |
| `frontend/`、`billing-service/`、`admin-service/` | 无 | — |

**Contracts**: 设计契约位于

- [volcano-key-validation.openapi.yaml](./contracts/volcano-key-validation.openapi.yaml)
- [error-classification.md](./contracts/error-classification.md)
- [consumer-merge-rules.md](./contracts/consumer-merge-rules.md)
- [upstream-volcano-models.md](./contracts/upstream-volcano-models.md)
- [v01-chat-models.md](./contracts/v01-chat-models.md)

实现时发布到 `shared/contracts/volcano-key-validation/v1/`。

**Data & Migrations**: 见 [data-model.md](./data-model.md)。**无迁移**。

**Security & Privacy**: 原始 Key 仅内存；响应/日志/指标脱敏；合成测试 Key；
`credential_ref` 不可逆。

内部 HTTP（analyze **C1** / 宪章 II）：

| 环境 | 允许形态 |
|------|----------|
| local/dev | 回环 + `X-Internal-Token`；flag 显式开启 |
| test/prod | 默认 **disabled**；启用则 MUST 仅私网/回环/网格可达，**禁止**公网监听；共享 token **不足**单独防护，优先 mTLS/服务身份 |
| 启动 | 非 local 启用且未满足绑定/隔离约束 → **fail-closed 不启动** |

配置键（实现名可微调，语义锁定）：`PROVIDER_VALIDATE_INTERNAL_ENABLED`（默认 false）、
`PROVIDER_VALIDATE_INTERNAL_TOKEN`、`PROVIDER_VALIDATE_BIND`（默认 `127.0.0.1` 或随
网关私网 listener）、`PROVIDER_VALIDATE_ALLOW_NON_LOOPBACK`（默认 false，仅运维私网例外）。

**Observability & Reliability**: `request_id`；指标
`provider_validate_total{platform,error_category}`、
`provider_validate_duration_seconds`、闸门拒绝计数；3s deadline；取消传播；
仅瞬时网络错误至多 1 次重试。

**Deployment & Rollback**: 契约与网关镜像；feature flag
`PROVIDER_VALIDATE_INTERNAL_ENABLED`。回滚：关 flag + 回退镜像。根 Makefile 仍为
唯一公开工作流入口。

## Constitution Check

*GATE: Phase 0 前通过；Phase 1 设计后复核。*

### Pre-Research Gate

| Gate | Result | Planned evidence |
|------|--------|------------------|
| Architecture and ownership | PASS | 仅 gateway 拥有适配器；无跨服务读库；无新服务 |
| Contracts and compatibility | PASS | OpenAPI + 分类 + 合并规则在实现前定义 |
| Security and privacy | PASS | Key 不落盘、脱敏；内部路由默认关 + 非 local 绑定 fail-closed（C1） |
| Data correctness | PASS | 无持久事实；额度精确类型/null 语义；禁止假 0 |
| Testing | PASS | 分类/契约/并发/取消/覆盖率规划 |
| Operations | PASS | 指标、截止、取消、invalid_response 可观测 |
| Delivery | PASS | 既有 make ci；flag 回滚 |
| Documentation language | PASS | 人工文档简体中文；契约标识英文 |

无宪章豁免。

### Post-Design Gate

| Gate | Result | Design evidence |
|------|--------|-----------------|
| Architecture and ownership | PASS | research D1/D9；Affected Components |
| Contracts and compatibility | PASS | [contracts/](./contracts/) |
| Security and privacy | PASS | research D9/D10；OpenAPI 部署说明；非 local 禁公网仅靠静态 token |
| Data correctness | PASS | [data-model.md](./data-model.md) 无假 0；QuotaReader 端口 |
| Testing | PASS | research D12；[quickstart.md](./quickstart.md) |
| Operations | PASS | 指标与 flag 回滚 |
| Delivery | PASS | 无迁移；镜像/flag |
| Documentation language | PASS | 本目录中文计划与研究 |

无宪章豁免。**注意**：工程草图 `GetBalance` 返回零值 **禁止** 实现。

## Project Structure

### Documentation (this feature)

```text
specs/006-volcano-key-validation/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── volcano-key-validation.openapi.yaml
│   ├── error-classification.md
│   ├── consumer-merge-rules.md
│   ├── upstream-volcano-models.md
│   └── v01-chat-models.md
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks — 未由本命令创建
```

### Source Code（计划落点）

```text
services/proxy-gateway/
├── internal/
│   ├── domain/
│   │   └── providervalid/
│   │       ├── types.go              # Request/Result/enums
│   │       ├── classify.go           # status → error_category
│   │       ├── classify_test.go
│   │       ├── allowlist.go
│   │       └── redaction.go
│   ├── application/
│   │   └── validate_credential.go    # 编排：闸门 → models → quota → 结果
│   ├── infrastructure/
│   │   └── platform/
│   │       └── volcano/
│   │           ├── client.go         # GET models
│   │           ├── client_test.go
│   │           ├── quota_noop.go     # NoopQuotaReader → quota_unavailable
│   │           └── fixtures/         # 金标 JSON（合成）
│   ├── concurrency/
│   │   └── validate_gate.go          # 全局/单凭证信号量
│   └── httpserver/
│       ├── server.go                 # 挂载 internal 路由（flag）
│       └── internal_validate.go
shared/contracts/volcano-key-validation/v1/   # 实现阶段从 specs 提升
```

**Structure Decision**: 遵循网关 Clean Architecture 方向（domain ← application ←
infrastructure/interfaces）。验证编排在 application；上游 I/O 在 volcano 包；
HTTP 仅作内部适配。不把业务服务加入 `compose.local.yml`。

## Complexity Tracking

> 无宪章违反项；本表留空。

| Violation | Why Needed | Simpler Alternative Rejected | ADR / Owner | Controls | Review or Expiry |
|-----------|------------|-----------------------------|-------------|----------|------------------|
| — | — | — | — | — | — |

## Phase 0 Summary

全部未知项已在 [research.md](./research.md) 决议，关键结论：

1. 归属 proxy-gateway  
2. 探活 `GET /models`  
3. 默认额度 `quota_unavailable`  
4. 并发 32/1、retry_after 默认 5/钳制 300  
5. 内部 HTTP + token；调用方合并规则外置  

## Phase 1 Summary

- [data-model.md](./data-model.md)：瞬时输入/结果值对象/闸门/allowlist  
- [contracts/](./contracts/)：OpenAPI、分类、合并、上游备忘、模型列表  
- [quickstart.md](./quickstart.md)：替身验收路径  

## Implementation Notes（供 /speckit-tasks）

建议任务波次：

1. 类型与枚举 + 分类器表驱动测试  
2. redaction + credential_ref  
3. allowlist 交集  
4. ValidateGate 32/1  
5. Volcano models client + fixtures  
6. NoopQuotaReader + 可注入 QuotaReader 成功/零额测试  
7. application 编排与 3s/cancel/retry  
8. internal HTTP + flag/token  
9. 指标与日志字段  
10. 契约提升 shared/ + quickstart 证据  
11. 官方文档复核勾选更新 upstream-volcano-models.md  

**Agent context update**: 仓库无独立 `update-agent-context` 脚本；活动功能上下文以
`specs/006-volcano-key-validation/` 与 `.specify/feature.json` 为准。实现阶段更新
Agents.md 活动功能条目（若项目惯例要求）。
