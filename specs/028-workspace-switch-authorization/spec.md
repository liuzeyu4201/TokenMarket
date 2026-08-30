# Feature Specification: 买家卖家工作区切换与路由授权

**Feature Branch**: `028-workspace-switch-authorization`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 买家/卖家工作区切换与路由授权"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF09-买家卖家工作区切换与路由授权.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 权限权威在哪？ → A: 账户角色是能力上限；当前工作区是生效透镜。UI 切换不是安全边界；服务端只信会话中的工作区，忽略请求体/头中的 workspace。
- Q: 双角色默认工作区？ → A: `both` 默认买家工作区。buyer-only 固定买家，seller-only 固定卖家。
- Q: 未授权切换？ → A: 403，并写审计。不得改变会话工作区。
- Q: 管理员？ → A: 不通过普通工作区获得管理员身份。
- Q: 两标签页？ → A: 同一 Web 会话共享一个工作区；服务端不得因客户端声称的工作区而串权。
- Q: Project/Connection 业务实体？ → A: 本 SF 用既有授权动作（proxy_key / seller_key / 自路由排除）作为工作区强制校验的可测代理；完整 Project 实体在 SF10+。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 双角色显式切换工作区 (Priority: P1)

`both` 用户在壳层选择买家或卖家工作区。切换成功后导航、展示与后续 API 都按新工作区生效。

**Why this priority**: 双角色是 V0.2 账号模型的核心。

**Independent Test**: both 用户从买家切到卖家后，会话摘要工作区为 seller；buyer-only 切换 seller 得 403。

**Acceptance Scenarios**:

1. **Given** 角色 both 且当前买家工作区，**When** 用户选择卖家工作区且通过 CSRF，**Then** 会话工作区变为 seller，界面标识更新。
2. **Given** 角色 buyer，**When** 请求切换到卖家工作区，**Then** 403、工作区不变、有审计。
3. **Given** 切换成功，**When** 查看壳层与工作台，**Then** 展示新工作区，前一工作区的筛选/草稿被清除。

---

### User Story 2 - 服务端按工作区强制授权 (Priority: P1)

每个写操作与查询判定同时校验会话身份、当前工作区、资源所有权与动作。客户端改 workspace 字段不能越权。

**Why this priority**: UI 不是安全边界。

**Independent Test**: both+买家工作区调用卖家动作 403；请求体填 seller 不能改变判定。

**Acceptance Scenarios**:

1. **Given** both 用户处于买家工作区，**When** 评估卖家动作，**Then** 403 `FORBIDDEN_ROLE`。
2. **Given** both 用户处于卖家工作区，**When** 评估买家代理 Key 动作，**Then** 403。
3. **Given** 任何授权请求，**When** 正文携带他人 user_id/role/workspace，**Then** 判定仍只使用会话事实。

---

### User Story 3 - 自有供给不得路由给自有买家 (Priority: P1)

双角色用户的连接不得成为其本人 Project/买家流量的候选。过滤后为空不得把本人资源加回。

**Why this priority**: 自买自卖排除是总纲硬约束。

**Independent Test**: 大量随机候选中，过滤结果永不包含 buyer 自己的 owner id。

**Acceptance Scenarios**:

1. **Given** 候选含本人与他人 active 资源，**When** 排除自有，**Then** 结果不含本人。
2. **Given** 过滤后为空，**When** 返回，**Then** 统一无候选，不把本人加回。
3. **Given** 10 万次随机模拟，**When** 每次排除，**Then** 自有资源选中次数 = 0。

---

### User Story 4 - 导航随工作区变化 (Priority: P2)

三类角色看到对应导航。buyer/seller 不能使用未授权工作区入口。管理员入口不出现在普通工作区。

**Why this priority**: 避免用户走错面，同时不把隐藏菜单当成授权。

**Independent Test**: buyer 无可用卖家切换；both 有切换；无「管理员」入口。

**Acceptance Scenarios**:

1. **Given** buyer 会话，**When** 看导航，**Then** 工作区为买家，切换卖家控件不可用或失败为 403。
2. **Given** both 会话，**When** 看导航，**Then** 可在买家/卖家之间切换。
3. **Given** 任意普通用户，**When** 看应用壳，**Then** 没有管理员工作区入口。

---

### Edge Cases

- 切换缺少 CSRF 或 Origin 非法：拒绝且不改工作区。
- 已是目标工作区的切换：幂等成功。
- 匿名调用授权或切换：401。
- 不在本 SF 实现完整 Project CRUD 或运营后台。

## Requirements *(mandatory)*

- **FR-001**: 会话 MUST 保存当前工作区 `buyer` 或 `seller`。
- **FR-002**: 权限上限 MUST 来自账户角色；切换 MUST NOT 授予未拥有角色。
- **FR-003**: 授权判定 MUST 使用会话工作区，MUST 忽略客户端 workspace/role/user_id。
- **FR-004**: both 处于买家工作区 MUST 不能执行卖家动作；处于卖家工作区 MUST 不能执行买家动作。
- **FR-005**: 写操作 MUST 同时校验 actor、workspace、ownership（若有资源）与 action。
- **FR-006**: 自路由排除 MUST 按不可伪造 owner id 去掉本人资源，空集不得回填。
- **FR-007**: 工作区切换成功 MUST 清除前一工作区的客户端筛选/草稿状态。
- **FR-008**: 未授权切换 MUST 403 且可审计。
- **FR-009**: 管理员身份 MUST NOT 通过普通工作区获得。
- **FR-010**: buyer-only / seller-only 的工作区 MUST 固定为对应角色。

### Engineering Requirements

- **ER-001 — Contracts**: 版本化工作区切换与授权评估契约；稳定 403 码。
- **ER-002 — Security**: CSRF + Origin；会话工作区为唯一透镜；负向越权测试。
- **ER-003 — Data**: expand-only 会话列；默认值按角色回填。
- **ER-004 — Performance**: 10 万次排除模拟在单测时限内完成。
- **ER-005 — Reliability**: 切换失败不改变工作区。
- **ER-006 — Observability**: 切换成功/拒绝可按 user 与 request ID 查询，无 token。
- **ER-007 — Accessibility**: 工作区切换控件可键盘操作并有当前工作区名称。

### Failure and Recovery

1. **Given** CSRF 无效，**When** 切换工作区，**Then** 403，工作区不变。
2. **Given** 并发两标签共享会话，**When** 一标签切换，**Then** 服务端以会话工作区为准，不接受另一标签伪造的 workspace。
3. **Given** 迁移回退，**When** 去掉工作区列，**Then** 授权回退为仅角色矩阵（旧行为）。

### Key Entities

- **Workspace**: `buyer` | `seller`，存在于 Web 会话。
- **AccountRole**: `buyer` | `seller` | `both`，能力上限。
- **AuthzDecision**: 允许或 403/401/404，含 policy 版本。
- **RouteCandidate**: owner_user_id + lifecycle；排除自有。

## Success Criteria

- **SC-001**: 三类角色授权矩阵正负向用例通过率 100%。
- **SC-002**: 篡改客户端 workspace/role/user_id 导致的越权成功次数 = 0。
- **SC-003**: 切换后会话工作区与界面标识一致；旧工作区草稿键不存在。
- **SC-004**: 未授权切换 403 且审计命中 ≥ 1。
- **SC-005**: 100_000 次模拟排除中自有资源选中次数 = 0。
- **SC-006**: 壳层无管理员工作区入口。

## Assumptions

- 复用 V0.1 `role-access-isolation` 判定、自路由排除、会话 cookie/CSRF。
- Project/Connection 实体尚未落地；proxy_key 代表买家面，seller_key 代表卖家面。
- 单 Web 会话（SF07）下多标签共享同一工作区状态。
