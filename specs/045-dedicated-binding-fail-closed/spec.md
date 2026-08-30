# Feature Specification: 专享绑定、降级与人工更换

**Feature Branch**: `045-dedicated-binding-fail-closed`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 专享绑定、降级与人工更换"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF25-专享绑定降级与人工更换.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 自动故障转移？ → A: 绝不。健康失败 100% 失败关闭。
- Q: 共享池回退？ → A: 绝不。其它连接调用次数必须为 0。
- Q: 资源迁移？ → A: 不迁移 files/batches/caches/fine_tuning/operations；旧资源命中旧连接或明确不可用。
- Q: 无买家确认？ → A: 保持 degraded，不更换。
- Q: 切换中间态？ → A: 请求只命中完整旧绑定或完整新绑定，不得混用凭据。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 专享独占与失败关闭 (Priority: P1)

dedicated Project 每协议绑一条空闲专享 Connection；异常后新请求失败关闭。

**Independent Test**: 第二条 Project 绑定同一 Connection 失败；unhealthy 后其它连接调用 = 0。

**Acceptance Scenarios**:

1. **Given** Connection 已绑定 Project A，**When** Project B 发布同一 Connection，**Then** 冲突拒绝。
2. **Given** 绑定连接 unhealthy / Binding degraded，**When** 新请求进入网关，**Then** 返回专享不可用，其它上游调用 0。
3. **Given** 同协议还存在健康共享连接，**When** 专享失败，**Then** 仍不回退共享池。

---

### User Story 2 - 人工更换需确认与影响清单 (Priority: P1)

更换前展示不迁移资源；买家确认、原因与 step-up 后才原子切换。

**Independent Test**: 未确认的更换次数 = 0；确认后审计含 actor、前后连接、原因。

**Acceptance Scenarios**:

1. **Given** 预览更换，**When** 查看影响，**Then** 明确列出 files/batches/caches/fine_tuning/operations 不迁移。
2. **Given** 买家未确认，**When** 提交更换，**Then** Binding 保持原连接与 degraded。
3. **Given** 确认+原因+step-up+新连接复验通过，**When** 更换，**Then** 新请求只命中新连接，旧连接 draining。

---

### User Story 3 - 旧资源不误送新连接 (Priority: P1)

亲和资源与在途请求按旧连接处理。

**Independent Test**: 钉在旧 resource_id 的后续请求 Connection 仍为旧 ID。

**Acceptance Scenarios**:

1. **Given** 已切换，**When** 带旧 resource 亲和的后续请求，**Then** 命中 draining 旧连接或明确不可用，不得使用新连接凭据。
2. **Given** 原子切换窗口，**When** 并发新请求，**Then** 每条请求的 ConnectionID 与凭据同属旧快照或新快照之一。

---

### Edge Cases

- 共享 Binding 拒绝更换接口。
- 新连接非 dedicated / 非空闲 / 协议不符 → 拒绝。
- 买家不确认时保持 degraded。

## Requirements *(mandatory)*

- **FR-001**: 一条 dedicated Connection MUST NOT 同时绑定两个 Project/protocol。
- **FR-002**: 绑定连接异常时新请求 MUST 失败关闭，MUST NOT 回退共享池。
- **FR-003**: 更换 MUST 列出不迁移资源并要求买家确认、原因与 step-up。
- **FR-004**: 切换 MUST 原子：请求只见完整旧或完整新绑定。
- **FR-005**: 旧资源操作 MUST 命中旧连接或明确不可用。
- **FR-006**: 旧连接 MUST 进入 draining，不得立即共享复用。
- **FR-007**: 更换 MUST 审计 actor、buyer confirmation、原因、前后连接与时间。

### Engineering Requirements

- **ER-001**: 扩展 `provider-binding/v1` 1.1.0（replace-preview / replace）。
- **ER-002**: 网关 `DedicatedSelector`；平台码 `DEDICATED_UNAVAILABLE`。
- **ER-003**: 覆盖率 ≥80%；独占、失败关闭、原子切换测试。

## Success Criteria

- **SC-001**: 同一 Connection 并发双绑成功次数 = 0。
- **SC-002**: unhealthy 后其它连接调用次数 = 0。
- **SC-003**: 未确认更换成功次数 = 0。
- **SC-004**: 切换窗口混用凭据次数 = 0。

## Assumptions

- 管理员后台灰度在 SF31；本 SF 提供买家确认 API 与审计。
- 真实 step-up 短信不在授权范围内；请求内 `step_up=true` 表示已完成挑战。
