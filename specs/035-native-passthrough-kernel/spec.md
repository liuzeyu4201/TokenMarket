# Feature Specification: 原生同协议透明代理核心

**Feature Branch**: `035-native-passthrough-kernel`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 原生同协议透明代理核心"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF18-原生同协议透明代理核心.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 如何识别协议？ → A: 先看路径前缀 `/openai|/anthropic|/vertex`，再看 Host（`openai.`/`anthropic.`/`vertex.`），再看目录 method+path 是否唯一命中一家厂商，再看 `anthropic-version` 或 Vertex `/v1/projects/`。无法判定则平台错误 `PROTOCOL_UNRESOLVED`，不得猜测转换。
- Q: 转换？ → A: 严禁 OpenAI↔Anthropic↔Vertex 字段/工具/错误转换。Volcano 兼容适配器保持独立路径，不得成为三厂商内核。
- Q: 请求体？ → A: 按字节流复制，不因本地 JSON 解析丢弃未知字段。安全可剥离 hop-by-hop、凭证、Cookie、内部网关头，清单写入契约。
- Q: 错误？ → A: 平台拒绝用稳定信封与 code；一旦拿到 upstream 响应，状态码与正文原样返回，不伪装为另一厂商错误。
- Q: 取消？ → A: 客户端断开取消可取消的 upstream；1 秒内可见。本 SF 用可注入 upstream 夹具，不发起付费厂商调用。完整路由选择属 SF23。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 三协议字节级透传 (Priority: P1)

买家按原生路径提交 OpenAI/Anthropic/Vertex 请求，平台只替换鉴权与目标地址，未知 JSON 字段与 query 仍在。

**Why this priority**: 同协议透传是 V0.2 数据面根基。

**Independent Test**: golden fixture 比较转发 body/query 与入站一致。

**Acceptance Scenarios**:

1. **Given** OpenAI chat 请求含未知字段，**When** 经 `/openai/v1/chat/completions` 透传，**Then** upstream 收到相同 JSON 字段。
2. **Given** Anthropic messages 请求，**When** 透传，**Then** 不改写为 Chat Completions 形状。
3. **Given** Vertex generateContent 路径，**When** 透传，**Then** path 模板变量保留，无跨协议改写。

---

### User Story 2 - 原生错误与平台信封分离 (Priority: P1)

upstream 4xx/5xx/429 原样返回；目录拒绝等平台错误用稳定 code，不伪装厂商 JSON。

**Independent Test**: upstream 400 正文等于客户端所见；目录未登记路径返回 `ENDPOINT_NOT_CATALOGED`。

**Acceptance Scenarios**:

1. **Given** upstream 返回 429 与原生 JSON，**When** 透传，**Then** 客户端收到同一状态码与正文。
2. **Given** 控制面路径，**When** 请求，**Then** 平台 `CONTROL_PLANE_NOT_ALLOWED`，不是厂商错误体。
3. **Given** 无法解析协议，**When** 请求，**Then** `PROTOCOL_UNRESOLVED`。

---

### User Story 3 - 取消、大小与超时 (Priority: P1)

客户端取消在 1 秒内传播；超大请求被平台拒绝；超时不把厂商错误体凭空编造。

**Independent Test**: 阻塞 upstream + cancel；超限 body。

**Acceptance Scenarios**:

1. **Given** 慢上游，**When** 客户端取消，**Then** 1 秒内 upstream 处理函数看到取消。
2. **Given** 请求体超过上限，**When** 提交，**Then** 平台拒绝且不转发。

---

### User Story 4 - 无转换代码路径 (Priority: P1)

自动测试证明内核包不存在跨协议转换。

**Independent Test**: 源码扫描 passthrough 包不引用 chatcompat、不出现跨协议字段映射。

**Acceptance Scenarios**:

1. **Given** passthrough 包，**When** 扫描 import 与标识符，**Then** 无 chatcompat、无 openai↔anthropic 映射函数。

---

### Edge Cases

- Cookie、Authorization（买家）、X-Internal-Token 不得转发到 upstream。
- 平台注入的 upstream Authorization / x-api-key 不得回传到客户端。
- SSE：Content-Type 为 event-stream 时按流刷新，不整包缓冲改写事件名。
- 本 SF 不实现综合评分路由（SF23）与完整 WS/文件亲和（SF22）；无可用 upstream 时平台 `NO_UPSTREAM`。
- Volcano `/v1/proxy/volcano/chat/completions` 保持既有适配器，不并入内核。

## Requirements *(mandatory)*

- **FR-001**: 内核 MUST 按 host/path/version 确定单一协议与目录端点。
- **FR-002**: 转发 MUST 保留原始 method、query、body 字节与允许的 headers。
- **FR-003**: 本地解析 MUST NOT 删除合法未知字段。
- **FR-004**: upstream 状态码、正文、SSE 事件与安全允许的响应头 MUST 原样返回。
- **FR-005**: 平台拒绝 MUST 使用稳定信封，且与 upstream 原生错误可区分。
- **FR-006**: MUST 执行请求/响应大小上限、超时与取消传播（≤1s）。
- **FR-007**: MUST NOT 存在 OpenAI↔Anthropic↔Vertex 转换路径。
- **FR-008**: hop-by-hop、凭证、Cookie、内部头 MUST 按契约剥离。

### Engineering Requirements

- **ER-001**: 新增契约 `native-passthrough/v1`（header 政策、平台错误码）。
- **ER-002**: 领域包 `internal/domain/passthrough`；HTTP 适配不解析业务 JSON。
- **ER-003**: 领域测试覆盖率 ≥80%；含 golden、取消、负向转换扫描。

## Success Criteria

- **SC-001**: 三协议 golden 转发等价通过率 100%。
- **SC-002**: 未知 JSON 字段被丢弃的次数 = 0。
- **SC-003**: 平台错误被写成厂商错误体的次数 = 0。
- **SC-004**: 取消未在 1s 内到达可取消 upstream 的次数 = 0。
- **SC-005**: 跨协议转换代码路径数 = 0。

## Assumptions

- Upstream 由可注入 Selector 提供（测试夹具 / fail-closed）；真实选路在 SF23。
- 不付费调用真实厂商。
