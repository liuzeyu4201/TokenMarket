# Feature Specification: 共享/专享供给模式与连接生命周期

**Feature Branch**: `034-supply-mode-lifecycle`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 共享/专享供给模式与连接生命周期"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF16-共享专享供给模式与连接生命周期.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 谁操作生命周期？ → A: 仅卖家工作区连接所有者。买家 403。
- Q: 模式何时锁定？ → A: 上架（listed）时锁定。draft/verified 可改模式。切换需先暂停/排空、解除绑定、无在途与未结算，回到 verified 后再改。
- Q: 状态集合？ → A: draft → verified → listed → bound（专享已绑定）→ paused → draining → retired。shared 不上 bound，保持 listed。
- Q: 专享/共享隔离？ → A: 专享不得进入共享池；共享不得充当专享故障回退。一个 Connection 同一时刻一种模式。专享最多绑定一个 Project+protocol。
- Q: 暂停与删除？ → A: pause 立即阻止新路由。drain 不允许新请求但保留在途亲和。删除/切模式在有绑定、在途或未结算时返回具体阻塞清单。retired 保留不可变 Connection ID 与卖家归属。V0.2 无真实结算时未结算端口默认为空，测试可注入。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 生命周期与模式锁定 (Priority: P1)

卖家验证后上架；上架后模式不可改；非法转换被拒。

**Why this priority**: 模式与状态是供给隔离的根。

**Independent Test**: 合法/非法转换表驱动；上架后 PATCH 模式 409。

**Acceptance Scenarios**:

1. **Given** draft 且验证成功，**When** 上架，**Then** listed，模式锁定。
2. **Given** listed，**When** 修改 supply_mode，**Then** 409 MODE_LOCKED。
3. **Given** listed，**When** 直接 retired，**Then** 非法转换。

---

### User Story 2 - 暂停、排空、删除阻塞 (Priority: P1)

pause 立即阻止新请求；有绑定/在途/未结算时切模式或删除返回阻塞原因。

**Why this priority**: 避免中断在途与账务。

**Independent Test**: pause 后 admits_new 立即为假；删除返回 blockers。

**Acceptance Scenarios**:

1. **Given** listed，**When** pause，**Then** 新路由不可见，时延 ≤1s。
2. **Given** 存在 active Binding，**When** 删除或切模式，**Then** 409 BINDING_ACTIVE。
3. **Given** 注入在途或未结算，**When** 删除，**Then** 返回对应阻塞码。

---

### User Story 3 - 共享/专享路由隔离 (Priority: P1)

专享连接不出现在共享池；共享不出现在专享绑定候选。并发绑定不能让一个专享连接属于两个 Project。

**Why this priority**: 产品硬隔离。

**Independent Test**: 属性测试共享列表无 dedicated；专享 unique 约束。

**Acceptance Scenarios**:

1. **Given** 一 shared listed 与一 dedicated listed，**When** 查询共享池，**Then** 仅 shared。
2. **Given** dedicated 已 bound，**When** 另一 Project 再绑定同一连接，**Then** 拒绝。
3. **Given** retired，**When** 按 Connection ID 查询元数据，**Then** 仍可见归属与模式，无明文。

---

### User Story 4 - 卖家 UI (Priority: P2)

连接页展示生命周期，可上架/暂停/排空/退役；上架后模式只读。

**Independent Test**: 按钮与状态文案；买家 forbidden。

**Acceptance Scenarios**:

1. **Given** 卖家 listed 连接，**When** 点暂停，**Then** 状态变为已暂停。
2. **Given** listed，**When** 查看模式控件，**Then** 不可改。

---

### Edge Cases

- 未验证 draft 不能上架。
- draining 不能 resume 到 listed，只能 retired（或完成排空后 retired）。
- 专享 listed 被 Binding 发布后进入 bound。
- 本 SF 不实现报价（SF17）与路由评分（SF24），但必须提供 admits_new 与池隔离查询。

## Requirements *(mandatory)*

- **FR-001**: 生命周期 MUST 含 draft、verified、listed、bound、paused、draining、retired。
- **FR-002**: 模式 MUST 在上架时锁定；非法切换 MUST 失败。
- **FR-003**: 一个 Connection MUST 仅一种模式；专享 MUST 最多一个活动 Binding。
- **FR-004**: shared MUST 可被多买家动态选；dedicated MUST NOT 进入共享池。
- **FR-005**: pause MUST 立即阻止新请求；drain MUST 允许在途按策略完成。
- **FR-006**: 删除/切模式 MUST 在有依赖时返回具体阻塞清单。
- **FR-007**: retired MUST 保留不可变 ID 与卖家归属；无明文。
- **FR-008**: 买家工作区 MUST 不能写生命周期。

### Engineering Requirements

- **ER-001**: 扩展 `provider-connection/v1` 至 1.3.0。
- **ER-002**: Alembic 约束与部分唯一索引。
- **ER-003**: 领域覆盖率 ≥80%；转换矩阵与隔离负向测试。

## Success Criteria

- **SC-001**: 合法/非法转换测试覆盖率 100%。
- **SC-002**: 专享连接出现在共享池的次数 = 0（反向亦然）。
- **SC-003**: pause 后 admits_new 为真的次数 = 0，且观察窗口 ≤1s。
- **SC-004**: 有依赖时切换/删除成功次数 = 0，且响应含阻塞码。
- **SC-005**: retired 后按 ID 仍能解析元数据且明文次数 = 0。

## Assumptions

- 在途与未结算在 V0.2 本阶段以可注入端口表示；SF22/SF28 接入真实观察。
- SF15 健康 healthy 是 listed 的前置；上架仍校验凭据可用。
