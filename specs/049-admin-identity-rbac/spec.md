# Feature Specification: 管理员身份、RBAC 与高风险操作审计

**Feature Branch**: `049-admin-identity-rbac`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 管理员身份、RBAC 与高风险操作审计"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF30-管理员身份RBAC与高风险操作审计.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 与用户身份关系？ → A: 完全分离的账号、Cookie、登录入口与 `/admin` 前缀；禁止把买家/卖家提升为 admin。
- Q: 高风险操作？ → A: 价格发布、路由回滚、专享更换、会话强退、冲正、break-glass；缺 MFA/step-up/原因任一则拒绝。
- Q: 凭据与账本？ → A: 管理员不能回读 upstream 明文，不能直接改余额，不能删除审计或账本。
- Q: 审计？ → A: 只追加，含 actor/role/action/target/reason/request/前后摘要/结果；自动脱敏。
- Q: break-glass？ → A: 受控开启、实时告警、事后关闭记录。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 身份隔离 (Priority: P1)

管理员与普通用户会话互不通用。

**Independent Test**: 用户 Cookie 访问 `/admin` 全部 401；管理员 Cookie 名与用户 Cookie 不同。

**Acceptance Scenarios**:

1. **Given** 有效用户 session Cookie，**When** 调用管理员接口，**Then** 401，且不建立管理员会话。
2. **Given** 管理员会话，**When** 使用用户 Cookie 名，**Then** 不被接受。
3. **Given** 买家账号，**When** 尝试提升为 admin，**Then** 拒绝。

---

### User Story 2 - RBAC 与高风险 step-up (Priority: P1)

角色最小权限；高风险必须 MFA、近期 step-up 和原因。

**Independent Test**: 矩阵每个允许/拒绝组合有测试；缺任一条件拒绝。

**Acceptance Scenarios**:

1. **Given** 价格只读角色，**When** 发布价格，**Then** 拒绝。
2. **Given** 账务写角色但无 step-up，**When** 冲正，**Then** 拒绝。
3. **Given** 已 MFA 且近期 step-up 并填写原因，**When** 被授权动作，**Then** 成功并写审计。

---

### User Story 3 - 审计完整性与 break-glass (Priority: P1)

审计不可改删；脱敏；break-glass 告警并关闭。

**Independent Test**: UPDATE/DELETE 审计失败；payload 无 secret；break-glass 产生告警与关闭记录。

**Acceptance Scenarios**:

1. **Given** 已写审计，**When** 修改或删除，**Then** 失败。
2. **Given** before/after 含 token，**When** 落盘，**Then** 被脱敏。
3. **Given** break-glass，**When** 开启，**Then** 告警；关闭后有评审记录。

---

### Edge Cases

- 只读角色不得执行高风险写。
- 直接改余额与读凭据动作为永久拒绝。

## Requirements *(mandatory)*

- **FR-001**: 管理员身份域 MUST 与用户分离；禁止角色提升。
- **FR-002**: RBAC MUST 覆盖支持、供给、价格/路由、账务、安全审计及只读。
- **FR-003**: 高风险操作 MUST 要求 MFA、近期 step-up 与原因。
- **FR-004**: 审计 MUST 记录 actor、role、action、target、reason、request、前后摘要、结果、来源。
- **FR-005**: 审计 MUST 只追加并具备完整性校验；应用不得改删。
- **FR-006**: 管理员 MUST NOT 回读明文凭据或直接改余额。
- **FR-007**: break-glass MUST 告警并形成事后关闭记录。
- **FR-008**: 审计前后值 MUST 脱敏，不含 secret/otp/token/正文。

### Engineering Requirements

- **ER-001**: 扩展 `audit/v1` 1.1.0；新增 `admin-identity/v1`。
- **ER-002**: admin-service 域 `adminauth`/`rbac`/`audit`；前缀 `/admin/v1`。
- **ER-003**: 覆盖率 ≥80%；RBAC 矩阵、身份隔离、step-up、防篡改测试。

## Success Criteria

- **SC-001**: 用户 Cookie 在管理员入口有效次数 = 0。
- **SC-002**: 无 MFA/step-up/原因的高风险成功次数 = 0。
- **SC-003**: 凭据回读与改余额成功次数 = 0。
- **SC-004**: 审计改删成功次数 = 0。
- **SC-005**: break-glass 无告警次数 = 0。

## Assumptions

- 运营后台页面属 SF31；本 SF 提供身份、授权、审计 API。
- 管理员不走用户手机 OTP 域；测试用独立口令+MFA 适配器。
