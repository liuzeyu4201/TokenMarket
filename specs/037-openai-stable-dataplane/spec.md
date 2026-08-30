# Feature Specification: OpenAI 稳定数据面全兼容

**Feature Branch**: `037-openai-stable-dataplane`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 OpenAI 稳定数据面全兼容"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF19-OpenAI稳定数据面全兼容.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 覆盖范围？ → A: 以冻结日 Endpoint Catalog 中 `provider=openai` 且 `stability=stable` 的记录为唯一范围，禁止手写端点白名单。
- Q: 真实厂商冒烟？ → A: 默认合同测试用上游夹具；`TOKENMARKET_OPENAI_SMOKE=1` 才打真实 OpenAI（本 Goal 不授权付费调用）。
- Q: Preview/Beta？ → A: 未 opt-in 失败关闭；不纳入本 SF 稳定覆盖率分母。
- Q: 控制面？ → A: 目录标记 `control_plane` 的 OpenAI 路径一律平台拒绝，不得透传到厂商。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 稳定推理端点原样透传 (Priority: P1)

Responses、Chat Completions、Models、音频、图像、嵌入、Moderation 等稳定推理按 OpenAI 原生形状转发。

**Why this priority**: 买家用官方 SDK 即可调用冻结范围内的推理面。

**Independent Test**: 目录全部 stable 推理记录合同测试 100% 通过；未知 JSON 字段保留。

**Acceptance Scenarios**:

1. **Given** 目录一条 openai stable 推理记录，**When** 原生路径调用，**Then** 上游收到相同 method/path/query/body，响应不被改写成其它厂商形状。
2. **Given** Chat Completions 或 Responses 带额外字段，**When** 透传，**Then** 额外字段仍在上游正文中。

---

### User Story 2 - 稳定资源生命周期 (Priority: P1)

Files、Uploads、Batches、Fine-tuning、Vector Stores、Assistants/Threads 等 stateful 资源在专享 Project 走亲和。

**Why this priority**: 异步与文件资源必须回到创建它的 Connection。

**Independent Test**: 创建→查询→删除钉住同一 Connection；shared 调用 stateful 返回 `DEDICATED_PROJECT_REQUIRED`。

**Acceptance Scenarios**:

1. **Given** dedicated Project，**When** 调用目录 stateful openai 端点，**Then** 允许进入内核并按亲和解析。
2. **Given** shared Project，**When** 调用同一 stateful 端点，**Then** `DEDICATED_PROJECT_REQUIRED` 且不转发。

---

### User Story 3 - Realtime 入口 (Priority: P1)

目录登记的 Realtime WebSocket/HTTP 数据面入口可用；连接亲和固定 Connection。

**Independent Test**: websocket `/v1/realtime` Upgrade 进入内核；shared 拒绝。

**Acceptance Scenarios**:

1. **Given** dedicated + catalog websocket，**When** Upgrade，**Then** 请求被承认为 realtime 数据面而非未登记 GET。
2. **Given** shared，**When** 同一入口，**Then** `DEDICATED_PROJECT_REQUIRED`。

---

### User Story 4 - 拒绝控制面与未登记路径 (Priority: P1)

组织/项目/API key 管理与未登记路径不得进入厂商。

**Independent Test**: 全部 openai `control_plane` 记录返回 `CONTROL_PLANE_NOT_ALLOWED`；未登记返回 `ENDPOINT_NOT_CATALOGED`。

**Acceptance Scenarios**:

1. **Given** `/v1/organization/*`，**When** 任意 method，**Then** 403 平台信封且上游未收到请求。
2. **Given** 未登记路径，**When** 调用，**Then** `ENDPOINT_NOT_CATALOGED`。

---

### Edge Cases

- Preview/beta openai 记录不计入稳定覆盖率；无 opt-in 为 `PREVIEW_NOT_ENABLED`。
- 流式终止原因、usage、错误形状与上游一致（夹具对比）。
- 真实冒烟缺省关闭，不得用 mock 冒充覆盖率分母。

## Requirements *(mandatory)*

- **FR-001**: 冻结目录全部 openai stable 记录 MUST 有合同测试且通过。
- **FR-002**: 原生请求 ID、错误、usage、流事件 MUST 原样转发（只替换平台鉴权）。
- **FR-003**: stateful/affinity 端点 MUST 仅 dedicated。
- **FR-004**: control-plane MUST 平台拒绝。
- **FR-005**: 未登记路径 MUST `ENDPOINT_NOT_CATALOGED`。
- **FR-006**: 不得引入跨协议转换或手写端点白名单。

### Engineering Requirements

- **ER-001**: 扩展 `native-passthrough/v1` 覆盖说明（1.2.0）。
- **ER-002**: 以嵌入目录生成测试表，覆盖率分母 = stable openai 记录数。
- **ER-003**: 领域测试覆盖率 ≥80%。

## Success Criteria

- **SC-001**: openai stable 合同测试通过率 = 100%。
- **SC-002**: 控制面被转发次数 = 0。
- **SC-003**: shared 调用 stateful 被放行次数 = 0。
- **SC-004**: 未登记路径进入上游次数 = 0。

## Assumptions

- 内核与亲和已由 SF18/SF22 提供；本 SF 补齐 OpenAI 目录覆盖与拒绝面。
- 付费真实冒烟列为发布阻塞项，不在本 Goal 执行。
