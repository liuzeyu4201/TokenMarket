# Feature Specification: 买家 Project 生命周期与模式

**Feature Branch**: `029-buyer-project-lifecycle`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 买家 Project 生命周期与模式"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF10-买家Project生命周期与模式.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 模式能否更改？ → A: 不能。创建时选择 shared 或 dedicated，写入不可变字段；任何更新接口不得接受 mode。
- Q: Binding 尚未落地如何启用协议？ → A: 创建时可声明协议集合。创建后的「启用协议」必须检查 Provider Binding；SF11 之前无 Binding 则该启用动作失败关闭。停用协议不删除历史。
- Q: 跨账号探测 ID？ → A: 不存在与无权访问返回同一 404 形状，正文无差异字段。
- Q: 删除与归档？ → A: 归档停止新代理请求但可查询审计。删除是逻辑终止；存在有效 Key/在途任务/未结算分录时拒绝并返回阻塞项。
- Q: 谁能操作？ → A: 仅买家工作区中的 Project 所有者。卖家工作区 403。管理员不走本接口。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 创建带不可变模式的 Project (Priority: P1)

买家在买家工作区创建 Project，必须选择共享或专享，并看到后果说明。名称在账号内可辨识。

**Why this priority**: Project 是后续 Binding/Key/路由的根。

**Independent Test**: 创建 shared 与 dedicated；再次提交 mode 变更被拒；数据库 mode 不变。

**Acceptance Scenarios**:

1. **Given** 买家工作区已登录，**When** 以合法名称、模式、至少一个协议创建，**Then** 得到全局不可猜测 ID、不可变 mode、状态进入允许的状态机。
2. **Given** 已有 Project，**When** 任何更新试图修改 mode，**Then** 被拒绝，mode 保持原值。
3. **Given** 同一账号已有同名（忽略大小写），**When** 再创建，**Then** 冲突，不产生第二行。

---

### User Story 2 - 状态机与归档 (Priority: P1)

Project 状态为 draft、active、suspended、archived。非法转换被拒。归档后禁止新代理请求，查询与审计仍可用。

**Why this priority**: 生命周期是授权与路由边界。

**Independent Test**: 合法转换成功；非法转换 409；归档后准入立即失败。

**Acceptance Scenarios**:

1. **Given** draft，**When** 激活，**Then** 变为 active。
2. **Given** archived，**When** 再激活或改 mode，**Then** 拒绝。
3. **Given** 刚归档，**When** 在 1 秒内询问是否允许新代理请求，**Then** 不允许。

---

### User Story 3 - 协议启用与删除检查 (Priority: P1)

多协议共享同一 Project 模式。创建后启用协议须逐个校验 Binding。删除在有依赖时返回具体阻塞项。

**Why this priority**: 防止无 Binding 的协议被当成可用，也防止误删。

**Independent Test**: 无 Binding 时启用失败；有阻塞项时删除列出 kind；清空后可逻辑删除或归档。

**Acceptance Scenarios**:

1. **Given** 无 Binding，**When** 对已有 Project 启用新协议，**Then** 失败关闭并说明缺少 Binding。
2. **Given** 存在有效依赖，**When** 删除，**Then** 409 且 data 含阻塞项类型。
3. **Given** 无依赖，**When** 删除，**Then** 逻辑终止，之后 GET 与无权访问同形 404。

---

### User Story 4 - 列表、详情与买家 UI (Priority: P2)

买家能列出自己的 Project、重命名、看到模式后果。卖家工作区看不到创建入口或得到 403。跨账号猜 ID 无泄漏。

**Why this priority**: 工作区边界必须在 UI 与 API 同时成立。

**Independent Test**: 所有者可读；他账号 404；卖家工作区创建 403。

**Acceptance Scenarios**:

1. **Given** 两个买家各有 Project，**When** A 用 B 的 ID GET/PATCH/DELETE，**Then** 与未知 ID 相同 404。
2. **Given** 卖家工作区，**When** POST 创建，**Then** 403。
3. **Given** 买家工作区，**When** 打开 Projects 页，**Then** 可创建（含模式后果文案）并看到列表。

---

### Edge Cases

- 空名称、过长名称、非法协议、空协议列表 → 校验失败。
- 停用协议不删除历史用量/账本行（本 SF 无账本时至少不级联删协议历史记录）。
- 不实现 Binding 实体、代理 Key 签发、专享连接绑定（后续 SF）。

## Requirements *(mandatory)*

- **FR-001**: 买家 MUST 能创建 Project，创建时 MUST 选择 shared 或 dedicated。
- **FR-002**: mode MUST 不可变；API/UI MUST NOT 提供修改 mode 的字段。
- **FR-003**: 名称在同一账号内 MUST 大小写不敏感唯一；ID MUST 全局不可猜测。
- **FR-004**: 状态 MUST 为 draft、active、suspended、archived；非法转换 MUST 拒绝。
- **FR-005**: 创建后启用协议 MUST 检查 Provider Binding；无 Binding 则失败关闭。
- **FR-006**: 停用协议 MUST NOT 删除历史用量或账本。
- **FR-007**: 删除 MUST 在存在有效 Key/在途任务/未结算分录时拒绝并返回阻塞项。
- **FR-008**: 归档后 MUST 禁止新代理请求，MUST 保留查询（未删除时）与审计。
- **FR-009**: 跨账号 ID 探测 MUST 与不存在不可区分。
- **FR-010**: 卖家工作区 MUST 不能创建或改买家 Project。

### Engineering Requirements

- **ER-001 — Contracts**: 扩展 `project/v1` OpenAPI（expand-only）；mode 无 PATCH。
- **ER-002 — Security**: 会话身份；工作区透镜；IDOR 404；CSRF 写操作。
- **ER-003 — Data**: PostgreSQL 约束：mode/status check、账号内名称唯一、mode 列无更新路径。
- **ER-004 — Performance**: 归档后准入检查 ≤1s。
- **ER-005 — Reliability**: 非法状态转换不改变行。
- **ER-006 — Observability**: 创建/归档/删除可按 owner 与 request ID 审计，无秘密。
- **ER-007 — Accessibility**: 创建表单有标签、模式后果与错误关联。

### Failure and Recovery

1. **Given** 并发同名创建，**When** 唯一约束冲突，**Then** 仅一行成功。
2. **Given** 无 Binding 启用协议，**When** 提交，**Then** 409，协议集合不变。
3. **Given** 迁移回退，**When** 去掉 projects 表，**Then** 不影响用户与会话表。

### Key Entities

- **Project**: 所有者、显示名、不可变 mode、状态、协议集合。
- **ProjectProtocol**: 协议名、是否启用、启用/停用时间。
- **DeletionBlocker**: kind（key/in_flight_task/unsettled_ledger）与引用。
- **ProjectAdmission**: 是否允许新代理请求。

## Success Criteria

- **SC-001**: shared/dedicated 创建与全部非法状态转换测试通过率 100%。
- **SC-002**: 通过 API 修改既有 mode 的成功次数 = 0。
- **SC-003**: 无 Binding 时启用新协议成功次数 = 0。
- **SC-004**: 有阻塞项时删除成功次数 = 0，且响应含阻塞类型。
- **SC-005**: 跨账号 GET 与未知 ID 的状态码与 code 一致。
- **SC-006**: 归档后 1 秒内准入允许新请求的次数 = 0。

## Assumptions

- Provider Binding、代理 Key 的 Project 作用域、账本分录在后续 SF 写入阻塞表。
- 本 SF 提供阻塞表与准入函数，供后续 SF 与网关复用。
- 买家 UI 使用既有设计系统组件。
