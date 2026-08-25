# Implementation Plan：火山方舟请求与响应兼容

**Branch**: `007-volcano-openai-compat` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

**Input**: `specs/007-volcano-openai-compat/spec.md`

## Summary

在 **proxy-gateway（Go）** 交付火山方舟 Chat Completions 的无状态适配能力：把
OpenAI-compatible 请求按 V0.1 允许列表过滤并映射模型，经数据面
`POST /api/v3/chat/completions` 出站，再把非流式响应与 SSE 事件转换成稳定兼容
形状，供 SF12/SF15 同进程调用、SF17 消费 usage 观察。

V0.1 默认：扩展采样集；`messages[].content` 原样转发；usage 缺失不填 0 且不否
定成功对象；缺截止则 60 秒硬上限；生成不重试；流式按「是否已交出兼容事件」
分界失败。无公开 HTTP、无持久化、无新微服务。

技术路径见 [research.md](./research.md)。

## Technical Context

**Language/Version**: Go 1.25.12（`services/proxy-gateway/`）

**Primary Dependencies**: 标准库 `net/http`、`bufio`、`context`、`encoding/json`；
既有 gateway 脚手架与 SF06（`providervalid` 分类/脱敏/`Retry-After`、volcano Base
URL）。不引入火山官方 SDK；不引入 Redis/PostgreSQL 于本功能。

**Storage**: **N/A** — 无持久化、无迁移。

**Testing**: Go `testing` + 表驱动；`net/http/httptest` 上游替身；黄金 JSON/SSE；
模糊解析；`-race`；domain/chat 适配包 ≥80% 行覆盖。

**Target Platform**: Linux 服务端与本地 macOS/Linux 主机进程（`make start` 中的
gateway）。本功能路径在 SF12/SF15 接线前仅由单测驱动。

**Project Type**: monorepo 网关领域增量 — 同进程 Chat Completions 适配端口

**Performance Goals**:

| 路径 | 目标 | 验收口径 | Spec |
|------|------|----------|------|
| 非流式转换（不含上游等待） | P95 < 5 ms | bench 写入 evidence；CI 不对 5 ms 墙钟 fail | SC-002 / ER-004 |
| 单条流事件转换 | P95 < 1 ms | 同上；CI 红线=禁止聚合完整流 | SC-002 / ER-004 |
| 缺截止时硬上限 | 60 s → `timeout` | 默认 CI | SC-002a / FR-014 |
| 流事件顺序/终止 | ≥10_000 确定性样本零丢失零重复零补造 | **默认 CI 红线** | SC-005 |

**Constraints**: 无状态；无 Key 落盘；无公开代理路由；仅 `volcano` Chat
Completions；生成不重试；临时类不得标永久 invalid；content 不在本层改写。

**Scale/Scope**: 1 平台适配器、1 版本契约目录、无新微服务、无 DB、无默认内部 HTTP。

### Affected Components

| Component | Owner / Planned change | Explicit non-change |
|-----------|------------------------|---------------------|
| `services/proxy-gateway/` | `domain/chatcompat`、application 编排、volcano chat/SSE 客户端、指标、测试 | 不实现 SF12 公开 Handler、不实现路由/鉴权/计量落账 |
| `shared/contracts/volcano-openai-compat/v1/` | 实现时提升本目录 `contracts/` | 不破坏 `volcano-key-validation/v1` |
| `ops/runbooks/`（按需） | `invalid_response` / `truncated_stream` 分诊 | 不新增公开 Make 动作 |
| `services/api-service/`、`frontend/`、`billing-service/`、`admin-service/` | 无 | — |

**Contracts**: 设计契约位于

- [volcano-openai-compat.openapi.yaml](./contracts/volcano-openai-compat.openapi.yaml)
- [error-classification.md](./contracts/error-classification.md)
- [request-field-allowlist.md](./contracts/request-field-allowlist.md)
- [header-allowlist.md](./contracts/header-allowlist.md)
- [sse-events.md](./contracts/sse-events.md)
- [usage-observation.md](./contracts/usage-observation.md)
- [upstream-volcano-chat.md](./contracts/upstream-volcano-chat.md)
- [consumer-notes.md](./contracts/consumer-notes.md)

实现时发布到 `shared/contracts/volcano-openai-compat/v1/`。

**Data & Migrations**: 见 [data-model.md](./data-model.md)。**无迁移**。

**Security & Privacy**: 卖家 Key 仅内存出站头；买家 Key 不得出站；消息正文默认
不记日志；合成夹具；`credential_ref` 不可逆。无新的公网监听。

**Observability & Reliability**: `request_id`；指标
`provider_chat_total{platform,stream,error_category}`、
`provider_chat_duration_seconds`、`provider_chat_truncated_total`；默认 60 s
截止；取消传播；生成禁止自动重试。

**Deployment & Rollback**: 仅网关镜像。无 flag 也可因尚未接线公开路由而无生产
流量。回滚：回退镜像。根 Makefile 仍为唯一公开工作流入口。

## Constitution Check

*GATE: Phase 0 前通过；Phase 1 设计后复核。*

### Pre-Research Gate

| Gate | Result | Planned evidence |
|------|--------|------------------|
| Architecture and ownership | PASS | 仅 gateway；同进程端口；无跨服务读库；无新服务 |
| Contracts and compatibility | PASS | OpenAPI + 允许列表 + SSE + usage + 分类在实现前定义 |
| Security and privacy | PASS | Key/正文脱敏；头允许列表；无公网新路由 |
| Data correctness | PASS | usage 整数/null 语义；禁止假 0；无持久事实 |
| Testing | PASS | 黄金/SSE/分类/截断分界/模糊/覆盖率 |
| Operations | PASS | 指标、60s 截止、取消、截断告警 |
| Delivery | PASS | 既有 make ci；无迁移；镜像回滚 |
| Documentation language | PASS | 人工文档简体中文；契约标识英文 |

无宪章豁免。工程规范中的巨型 `PlatformAdapter`（含 `GetBalance` 浮点余额）
**不**作为本功能实现形状；采用窄端口，避免把已否决的零额度探活带进 chat 路径。

### Post-Design Gate

| Gate | Result | Design evidence |
|------|--------|-----------------|
| Architecture and ownership | PASS | research D1；Affected Components |
| Contracts and compatibility | PASS | [contracts/](./contracts/) |
| Security and privacy | PASS | research D10/D12；头允许列表 |
| Data correctness | PASS | [data-model.md](./data-model.md)；[usage-observation.md](./contracts/usage-observation.md) |
| Testing | PASS | research D13；[quickstart.md](./quickstart.md) |
| Operations | PASS | D6/D14；runbook 计划 |
| Delivery | PASS | 无迁移；镜像回滚 |
| Documentation language | PASS | 本目录中文计划与研究 |

无宪章豁免。

## Project Structure

### Documentation (this feature)

```text
specs/007-volcano-openai-compat/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── volcano-openai-compat.openapi.yaml
│   ├── error-classification.md
│   ├── request-field-allowlist.md
│   ├── header-allowlist.md
│   ├── sse-events.md
│   ├── usage-observation.md
│   ├── upstream-volcano-chat.md
│   └── consumer-notes.md
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks — 未由本命令创建
```

### Source Code（计划落点）

```text
services/proxy-gateway/
├── internal/
│   ├── domain/
│   │   └── chatcompat/
│   │       ├── types.go              # Request/Result/StreamEvent/enums
│   │       ├── allowlist.go          # 顶层字段过滤与取值
│   │       ├── modelmap.go           # 公开 ↔ 上游模型
│   │       ├── usage.go              # usage 完整性
│   │       └── classify.go           # 复用/包装 providervalid 映射
│   ├── application/
│   │   └── chat_completions.go       # 截止、过滤、出站、标准化
│   ├── infrastructure/
│   │   └── platform/
│   │       └── volcano/
│   │           ├── chat_client.go    # POST chat/completions
│   │           ├── sse.go            # 增量 SSE 解析
│   │           └── fixtures/         # 合成金标 JSON/SSE
│   └── observability/
│       └── chat_metrics.go
shared/contracts/volcano-openai-compat/v1/   # 实现阶段从 specs 提升
```

**Structure Decision**: 遵循网关 Clean Architecture（domain ← application ←
infrastructure）。Chat 编排在 application；上游 I/O 与 SSE 在 volcano 包；
SF12/SF15 只依赖 application/domain 端口。不把业务服务加入 `compose.local.yml`。
不在本功能实现规范草稿里的全量 `PlatformAdapter` 接口。

## Complexity Tracking

> 无宪章违反项；本表留空。

| Violation | Why Needed | Simpler Alternative Rejected | ADR / Owner | Controls | Review or Expiry |
|-----------|------------|-----------------------------|-------------|----------|------------------|
| — | — | — | — | — | — |

## Phase 0 Summary

全部未知项已在 [research.md](./research.md) 决议，关键结论：

1. 归属 proxy-gateway；同进程端口；无默认内部 HTTP  
2. 上游 `POST /api/v3/chat/completions`（官方已 OpenAI 兼容）→ 薄适配  
3. 扩展采样允许列表；content 原样转发  
4. usage 观察与成功对象解耦；禁止假 0  
5. 默认 60s 硬截止；生成不重试  
6. 流式失败分界 = 是否已交出兼容事件  

## Phase 1 Summary

- [data-model.md](./data-model.md)：瞬时请求/结果/流事件/usage 观察  
- [contracts/](./contracts/)：OpenAPI、允许列表、SSE、上游备忘、调用方说明  
- [quickstart.md](./quickstart.md)：替身验收路径  

## Implementation Notes（供 /speckit-tasks）

建议任务波次：

1. `chatcompat` 类型、枚举、允许列表与越界测试  
2. 模型映射 + allowlist 未知模型拒绝  
3. usage 三种状态不变量测试  
4. 非流式请求过滤黄金测试 → 实现  
5. volcano `ChatClient` + fixtures（401/429/200）  
6. 非流式响应标准化（choices 缺失 vs usage 缺失）  
7. SSE 分帧解析器 + 模糊/拆包合包  
8. 流式失败分界（零事件结构化错误 / 已出事件 truncated）  
9. application 编排：60s 截止、取消、禁止重试  
10. 头允许列表与脱敏  
11. 指标与结构化日志  
12. 契约提升 shared/ + quickstart 证据  
13. 官方文档复核勾选 `upstream-volcano-chat.md`  
14. SC-005：`sse_scale_test.go` ≥10_000 确定性事件进默认 CI  
15. SC-002：`go test -bench` 写入 evidence，不对 5 ms/1 ms 墙钟 fail CI  

**Agent context update**: 仓库无独立 `update-agent-context` 脚本；活动功能上下文以
`specs/007-volcano-openai-compat/` 与 `.specify/feature.json` 为准。实现阶段按惯例
更新 Agents.md 活动功能条目。
