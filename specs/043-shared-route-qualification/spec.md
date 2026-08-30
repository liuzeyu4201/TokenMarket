# Feature Specification: 共享路由资格过滤与自买自卖排除

**Feature Branch**: `043-shared-route-qualification`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 共享路由资格过滤与自买自卖排除"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF23-共享路由资格过滤与自买自卖排除.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 评分能否挽救硬门槛？ → A: 不能。
- Q: 专享连接？ → A: 永不进入共享候选集。
- Q: 自买自卖？ → A: 排除买家本人及受其控制的卖家 Connection。
- Q: 无候选？ → A: 不调用 upstream，平台 `NO_UPSTREAM`。
- Q: 快照？ → A: 每次过滤使用一个完整候选快照，可重放。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 硬门槛过滤 (Priority: P1)

共享路由先过滤 mode/protocol/endpoint/capability/model/region/health/capacity/price。

**Independent Test**: 每个门槛单独失败夹具。

**Acceptance Scenarios**:

1. **Given** dedicated 连接，**When** 共享请求过滤，**Then** 因 mode 排除。
2. **Given** 协议不匹配，**When** 过滤，**Then** 不入选。
3. **Given** unhealthy 或容量 0，**When** 过滤，**Then** 不入选。

---

### User Story 2 - 自买自卖排除 (Priority: P1)

买家不得命中自己或控制的卖家连接。

**Independent Test**: 双角色 owner 相同选择次数 0。

**Acceptance Scenarios**:

1. **Given** 连接 seller_owner=买家，**When** 共享路由，**Then** 排除且 self_trade_excluded=true。
2. **Given** 仅自有连接合格其它门槛，**When** 过滤，**Then** 候选为空且不转发。

---

### User Story 3 - 无候选失败关闭 (Priority: P1)

无合格连接不降级。

**Independent Test**: upstream 调用次数 0。

---

### Edge Cases

- preview 需 opt-in 且 capability。
- 同一快照重放候选集相同。

## Requirements *(mandatory)*

- **FR-001**: 硬过滤 MUST 先于评分且版本化原因码。
- **FR-002**: 专享 MUST 不进共享池。
- **FR-003**: 自买自卖 MUST 排除。
- **FR-004**: 无候选 MUST 不调用 upstream。
- **FR-005**: 决策 MUST 可重放。
- **FR-006**: 决策 MUST NOT 含凭据。

### Engineering Requirements

- **ER-001**: 扩展 `route-decision/v1` 1.1.0。
- **ER-002**: `qualify` 包 + Selector 适配。
- **ER-003**: 覆盖率 ≥80%；属性测试。

## Success Criteria

- **SC-001**: 硬门槛失败进入候选次数 = 0。
- **SC-002**: 自买自卖选中次数 = 0。
- **SC-003**: 无候选 upstream 调用 = 0。

## Assumptions

- SF24 在合格集上评分；本 SF 只产出合格集。
