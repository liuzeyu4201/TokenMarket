# Feature Specification: Anthropic 稳定数据面全兼容

**Feature Branch**: `038-anthropic-stable-dataplane`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 Anthropic 稳定数据面全兼容"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF20-Anthropic稳定数据面全兼容.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 覆盖范围？ → A: 冻结目录 `provider=anthropic` 且 `stability=stable` 为唯一分母。
- Q: Beta Files 等？ → A: 无 Project opt-in 必须平台拒绝；不计入稳定覆盖率。
- Q: 真实冒烟？ → A: 默认夹具；`TOKENMARKET_ANTHROPIC_SMOKE=1` 才打真实（本 Goal 不授权付费调用）。
- Q: 协议形状？ → A: 不得改写成 OpenAI 风格；保留 anthropic-version、错误信封与 SSE 事件名。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Messages 原样透传 (Priority: P1)

stable Messages（含 content blocks、工具、流式）按 Anthropic 原生形状转发。

**Independent Test**: 目录全部 anthropic stable 合同测试 100%；SSE 事件顺序与夹具一致。

**Acceptance Scenarios**:

1. **Given** POST `/v1/messages` 带未知字段，**When** 透传，**Then** 上游正文不变且不为 OpenAI `choices` 形状。
2. **Given** 上游依次发送 message_start、content_block_delta、message_stop，**When** 流式转发，**Then** 客户端顺序相同。

---

### User Story 2 - Batches / tokens / models (Priority: P1)

Message Batches 生命周期仅 dedicated；token count 与 models 可在 shared 调用。

**Independent Test**: 创建→查询钉住 Connection；shared 调 batches 被拒；count_tokens/models 允许 shared。

**Acceptance Scenarios**:

1. **Given** dedicated，**When** POST batches 返回 id 后 GET 该 id，**Then** 使用同一 Connection。
2. **Given** shared，**When** POST `/v1/messages/batches`，**Then** `DEDICATED_PROJECT_REQUIRED`。

---

### User Story 3 - 拒绝控制面与 Beta (Priority: P1)

api_keys/org/users 控制面与未 opt-in Beta files 不得透传。

**Independent Test**: 全部 anthropic control_plane 不转发；files 无 opt-in 为 preview 拒绝。

**Acceptance Scenarios**:

1. **Given** `/v1/api_keys`，**When** GET，**Then** `CONTROL_PLANE_NOT_ALLOWED`。
2. **Given** `/v1/files` 且未 opt-in，**When** POST，**Then** 平台拒绝。

---

### Edge Cases

- 上游 429 与 retry-after 原样返回。
- 未登记路径 `ENDPOINT_NOT_CATALOGED`。

## Requirements *(mandatory)*

- **FR-001**: 全部 anthropic stable 记录 MUST 有合同测试且通过。
- **FR-002**: Messages SSE 事件名与顺序 MUST 不被改写。
- **FR-003**: `anthropic-version` 等必要版本头 MUST 转发。
- **FR-004**: stateful batches MUST 仅 dedicated 并亲和钉住。
- **FR-005**: control-plane 与未 opt-in beta MUST 平台拒绝。
- **FR-006**: 不得引入 OpenAI↔Anthropic 转换。

### Engineering Requirements

- **ER-001**: `native-passthrough/v1` 1.3.0 增加 anthropic-stable 说明。
- **ER-002**: 测试表由嵌入目录生成。
- **ER-003**: 包覆盖率 ≥80%。

## Success Criteria

- **SC-001**: anthropic stable 合同通过率 = 100%。
- **SC-002**: 控制面转发次数 = 0。
- **SC-003**: 流事件被改写成 OpenAI chunk 的次数 = 0。

## Assumptions

- 内核已由 SF18/SF22 提供。付费冒烟为发布阻塞项。
