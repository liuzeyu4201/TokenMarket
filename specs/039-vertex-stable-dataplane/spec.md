# Feature Specification: Google Vertex 稳定数据面全兼容

**Feature Branch**: `039-vertex-stable-dataplane`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 Google Vertex 稳定数据面全兼容"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF21-GoogleVertex稳定数据面全兼容.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 覆盖范围？ → A: 冻结目录 `provider=vertex` 且 `stability=stable`。
- Q: 路径中的 project/location？ → A: 内核原样转发，不得改写为其它项目/区域；越权拒绝由 Connection/Binding 在后续路由 SF 失败关闭，本 SF 锁定路径不被内核替换。
- Q: 真实冒烟？ → A: 默认夹具；`TOKENMARKET_VERTEX_SMOKE=1` 才打真实（本 Goal 不授权付费）。
- Q: 平台错误？ → A: 不得伪装成 `google.rpc.Status`。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 稳定生成与查询原样透传 (Priority: P1)

generate/stream/count/embed/predict 等稳定方法走原生 Vertex 路径。

**Independent Test**: 全部 vertex stable 合同测试 100%；未知 JSON 保留；平台错误非 google.rpc。

**Acceptance Scenarios**:

1. **Given** generateContent 带额外字段，**When** 透传，**Then** 上游正文与路径中的 project/location 不被内核改写。
2. **Given** 未登记路径，**When** 调用，**Then** `ENDPOINT_NOT_CATALOGED` 且信封不含 `google.rpc`。

---

### User Story 2 - 有状态资源与 operation 亲和 (Priority: P1)

batch、cached content、tuning、long-running operation 仅 dedicated，后续轮询钉住原 Connection。

**Independent Test**: 创建响应 `name` 登记后 GET operation 使用同一 Connection；shared 被拒。

**Acceptance Scenarios**:

1. **Given** dedicated predictLongRunning 返回 operation name，**When** GET 该 operation，**Then** SelectConnection 为创建时 Connection。
2. **Given** shared，**When** POST batchPredictionJobs，**Then** `DEDICATED_PROJECT_REQUIRED`。

---

### User Story 3 - 拒绝 IAM 控制面 (Priority: P1)

getIamPolicy/setIamPolicy/endpoints 管理不得透传。

**Independent Test**: 全部 vertex control_plane 不转发。

**Acceptance Scenarios**:

1. **Given** `:getIamPolicy`，**When** POST，**Then** `CONTROL_PLANE_NOT_ALLOWED`。
2. **Given** v1beta1 generate 无 opt-in，**When** POST，**Then** `PREVIEW_NOT_ENABLED`。

---

### Edge Cases

- 流式 streamGenerateContent 不改写成 OpenAI chunk。
- 列表类 stateful 无资源 ID 时不随机亲和，只要求 dedicated。

## Requirements *(mandatory)*

- **FR-001**: 全部 vertex stable 记录 MUST 合同测试通过。
- **FR-002**: project/location/resource name MUST 原样出现在上游路径。
- **FR-003**: operation/batch/cache/tuning 后续请求 MUST 亲和 fail-closed。
- **FR-004**: control-plane MUST 平台拒绝且不得写成 google.rpc.Status。
- **FR-005**: 未 opt-in preview MUST 拒绝。
- **FR-006**: 不得跨协议转换。

### Engineering Requirements

- **ER-001**: native-passthrough 1.4.0 vertex-stable 说明。
- **ER-002**: 目录生成测试表；ResourceID 忽略 Google context 变量。
- **ER-003**: 包覆盖率 ≥80%。

## Success Criteria

- **SC-001**: vertex stable 合同通过率 = 100%。
- **SC-002**: 控制面转发次数 = 0。
- **SC-003**: 平台错误伪装为 google.rpc.Status 次数 = 0。

## Assumptions

内核与亲和已存在。Binding 项目越权的完整鉴权在路由/连接 SF 关闭；本 SF 保证路径不被内核替换。
