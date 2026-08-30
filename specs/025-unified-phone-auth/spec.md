# Feature Specification: 统一手机号验证注册登录

**Feature Branch**: `025-unified-phone-auth`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 统一手机号验证注册登录"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF06-统一手机号验证注册登录.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 验证前如何防枚举？ → A: 发送验证码始终同一 202 形状；不通过状态码、文案、重试额度或明显时延泄露账号是否存在。
- Q: 新用户何时建账号？ → A: OTP 成功且手机号无 active 账户时不建用户行；签发短时资料补全凭证。昵称+角色提交成功后原子创建账户与会话。中断不产生半账号。
- Q: 无 OTP 的旧注册接口？ → A: 公开 `POST /api/v1/auth/register` 无补全凭证时必须拒绝，避免 `PHONE_ALREADY_REGISTERED` 枚举。
- Q: 停用/软删账户？ → A: 仍走中性 202；不建立可用登录或补全路径（decoy）。
- Q: 角色？ → A: `buyer` / `seller` / `both`。
- Q: 密码/OAuth/SSO？ → A: 不做。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 同一入口发送验证码且不泄露是否注册 (Priority: P1)

访客只看到一个手机号入口。已注册与未注册号码得到相同受理响应。

**Independent Test**: 对 active、未知、suspended、deleted 号码请求验证码，比较状态码、JSON 键与中性文案。

**Acceptance Scenarios**:

1. **Given** 合法中国大陆手机号无论是否已注册，**When** 请求验证码且通过限流，**Then** HTTP 202、相同信封结构与中性文案，不声明账号存在或短信已送达。
2. **Given** 未知手机号，**When** 系统受理，**Then** 内部可为该号码建立可投递挑战（以便后续注册），但对外响应与已注册号码无法区分。
3. **Given** 短信供应商整体故障，**When** 请求验证码，**Then** 所有号码类别得到同一暂时失败，仍不泄露存在性。

---

### User Story 2 - 已有用户验证后直接登录 (Priority: P1)

active 用户提交正确验证码后建立唯一会话并进入平台。

**Independent Test**: 合成 active 用户走统一入口，正确 OTP 后有会话 cookie，无用户行新增。

**Acceptance Scenarios**:

1. **Given** active 用户与未过期正确验证码，**When** 提交验证，**Then** 挑战一次性消费、建立会话、撤销旧会话。
2. **Given** 错误、过期、已使用验证码，**When** 提交，**Then** 不建会话；错误、过期、已使用均有自动化覆盖且不可重放。

---

### User Story 3 - 新用户验证后补全资料并自动登录 (Priority: P1)

未知手机号验证成功后进入昵称与角色补全；保存成功后原子创建账户并自动登录。中断不留半账号。

**Independent Test**: 未注册号码完成 OTP → 补全 → 恰好一条用户且已登录；只 OTP 不补全则用户表无该号码。

**Acceptance Scenarios**:

1. **Given** 未知号码 OTP 正确，**When** 验证成功，**Then** 不创建用户行，返回资料补全下一步，并签发短时补全凭证（非正式会话）。
2. **Given** 有效补全凭证，**When** 提交合法昵称与角色，**Then** 原子创建 active 账户与会话，界面进入已登录。
3. **Given** 用户在补全前离开，**When** 查询数据库，**Then** 不存在该手机号的用户行。
4. **Given** 50 个并发补全同一手机号，**When** 全部完成，**Then** 只有一个账号。

---

### User Story 4 - 限流、短信故障与无明文验证码 (Priority: P2)

按手机号、IP/设备与全局限流；冷却后可重试。短信失败有明确状态。日志无明文验证码。

**Independent Test**: 触发手机号/IP 限流后冷却可恢复；日志扫描无 OTP 明文。

**Acceptance Scenarios**:

1. **Given** 同一手机号或 IP 达到获取上限，**When** 再请求，**Then** 429 中性提示，不泄露账号存在。
2. **Given** 冷却期结束，**When** 合法用户再请求，**Then** 可再次受理。
3. **Given** 任何认证路径，**When** 检查日志与普通库字段，**Then** 无明文验证码。

---

### Edge Cases

- 旧 `POST /register` 无补全凭证 → 拒绝，不得用占用冲突枚举。
- 补全凭证过期或已用 → 必须重新验证码，不建账号。
- 验证成功后、补全前该号码被他人抢注（几乎仅并发）→ 唯一约束，失败者不得绑到他人会话。
- 不实现密码、OAuth、SSO。

## Requirements *(mandatory)*

- **FR-001**: 发送验证码对外 MUST 对已注册/未注册使用同一可接受响应。
- **FR-002**: 验证码单次有效、短时过期、限制尝试；不可重放。
- **FR-003**: 限流维度 MUST 含规范化手机号、客户端 IP；冷却后可重试。
- **FR-004**: active 用户 OTP 成功 MUST 创建会话且不走补全。
- **FR-005**: 无用户 OTP 成功 MUST NOT 插入 users 行；MUST 签发补全凭证。
- **FR-006**: 补全提交 MUST 原子创建用户+会话。
- **FR-007**: 角色 MUST 为 buyer、seller、both；手机号规范化与唯一性由数据库约束保证。
- **FR-008**: 无补全凭证的公开注册 MUST 拒绝。
- **FR-009**: 日志/trace/普通库字段 MUST NOT 存明文验证码。
- **FR-010**: 不实现密码、OAuth、SSO。
- **FR-011**: 停用/删除账户 MUST 保持中性发送响应且 MUST NOT 登录或补全建号。

### Engineering Requirements

- **ER-001 — Contracts**: 版本化 OpenAPI；会话与补全响应可区分且验证前形状一致。
- **ER-002 — Security**: 补全凭证 HttpOnly+Secure+host-only；OTP 仅摘要；防枚举。
- **ER-003 — Data**: 用户行仅在补全事务中出现；phone unique。
- **ER-004 — Performance**: 发送验证码路径保持既有反枚举时延门禁。
- **ER-005 — Reliability**: 短信供应商整体故障统一失败；号码级失败不改变对外 202 形状。
- **ER-006 — Observability**: 审计事件不包含 OTP；补全成功/失败可计数。
- **ER-007 — Accessibility**: 统一入口表单可键盘操作，错误与字段关联。

### Failure and Recovery

1. **Given** 补全事务中唯一约束冲突，**When** 并发提交，**Then** 仅一胜者建号登录，失败者无会话。
2. **Given** 重复提交同一验证码，**When** 第二次，**Then** 失败且不新建会话/凭证。
3. **Given** 进程在 OTP 成功后、补全前提交前重启，**When** 用户返回，**Then** 无半账号；凭证仍有效则可补全，否则重新获取验证码。

### Key Entities

- **VerificationChallenge**: 可投递或 decoy；注册用途可保存规范化手机号以便投递。
- **ProfileCompletionIntent**: 短时、一次性、绑定已消费挑战与手机号。
- **User**: 仅补全成功后存在。
- **AuthSession**: 登录或补全成功后签发。

## Success Criteria

- **SC-001**: 四类号码发送验证码公开形状一致率 100%。
- **SC-002**: 错误/过期/已用 OTP 建会话数为 0。
- **SC-003**: 50 并发补全同一号码用户行数 = 1。
- **SC-004**: 仅 OTP 不补全时该号码用户行数 = 0。
- **SC-005**: 补全成功后存在会话且自动进入已登录状态。
- **SC-006**: 日志夹具中明文 OTP 命中 = 0。

## Assumptions

- 复用 V0.1 中国大陆手机号规范化、HttpOnly 会话、单会话、202-before-dispatch、合成短信适配器。
- 设备维度限流：无稳定设备 ID 时以可信客户端 IP 作为设备/来源代理（与 V0.1 一致），并保留手机号与全局限流。
- UI E2E 浏览器矩阵在 SF08/SF34 补齐；本 SF 交付组件/集成测试与可键盘表单。
