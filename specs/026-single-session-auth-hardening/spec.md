# Feature Specification: 单会话与认证安全加固

**Feature Branch**: `026-single-session-auth-hardening`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 单会话与认证安全加固"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF07-单会话与认证安全加固.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 单会话覆盖哪些凭据？ → A: 仅平台 Web 会话。代理 Key 可同时服务多个合法客户端，不受 Web 登录替换、退出或世代提升影响。
- Q: 旧会话如何跨节点失效？ → A: 新登录在同一事务提升账户会话世代并撤销旧 Web 会话；所有节点在 1 秒内拒绝旧世代。缓存只可加速，不可让已撤销会话复活。
- Q: 异常登录如何提醒？ → A: 不发送邮件/短信。在账户安全页展示会话摘要与最近认证事件；新登录替换旧会话后，被替换设备下次请求得到会话失效，当前设备可见替换结果。
- Q: 退出范围？ → A: 支持退出当前会话与全部 Web 会话（提升世代）。代理 Key 仍不受影响。
- Q: 密码/OAuth/SSO/JWT 浏览器会话？ → A: 不做。继续手机号验证码 + HttpOnly 会话 cookie。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 第二台设备登录立即挤掉第一台 (Priority: P1)

已登录用户在另一设备完成验证后，旧设备在任意入口节点上都不再被当作已登录。

**Why this priority**: 单会话是本 SF 的核心安全不变量。

**Independent Test**: 同一账号先后在两个客户端登录；查当前有效会话数为 1；旧 cookie 在随后 1 秒内的引导/受保护请求失败。

**Acceptance Scenarios**:

1. **Given** 账号已有有效 Web 会话 A，**When** 同一账号在另一客户端成功登录，**Then** 只保留会话 B，A 被撤销且世代已提升。
2. **Given** 会话 A 已被替换，**When** 任意节点在 1 秒内收到带 A 的请求，**Then** 返回未认证/会话失效，不得继续授权。
3. **Given** 会话替换完成，**When** 检查该账号代理 Key，**Then** Key 仍可用、未被禁用或轮换。

---

### User Story 2 - 主动退出立即生效 (Priority: P1)

用户从当前设备退出，或从安全页结束全部 Web 会话后，旧 cookie 立即不可用。

**Why this priority**: 丢失设备与共享电脑需要可验证的立即失效。

**Independent Test**: 退出后同一 cookie 引导失败；全部退出后该账号无有效 Web 会话；审计可按账号与 request ID 查到退出。

**Acceptance Scenarios**:

1. **Given** 有效会话，**When** 用户退出当前会话，**Then** 该 cookie 立即失效，响应清除浏览器会话。
2. **Given** 有效会话，**When** 用户结束全部 Web 会话，**Then** 该账号无有效 Web 会话，世代已提升。
3. **Given** 退出成功，**When** 查询认证审计，**Then** 可按账号与 request ID 找到退出记录且不含 token。

---

### User Story 3 - 账户安全页看到当前会话摘要 (Priority: P2)

已登录用户打开账户安全页，看到当前会话的脱敏摘要（不含凭据），以及最近登录/退出结果。

**Why this priority**: 用户需要可感知的异常登录与会话状态，但不暴露凭据。

**Independent Test**: 已登录打开安全页得到摘要；匿名被拒绝；摘要不含 cookie/token 明文。

**Acceptance Scenarios**:

1. **Given** 已登录用户，**When** 打开账户安全页，**Then** 看到当前会话脱敏摘要（签发时间、过期、IP/设备摘要）与最近认证事件结果。
2. **Given** 匿名访问，**When** 请求安全页数据，**Then** 未认证拒绝。
3. **Given** 任何安全页响应，**When** 检查正文，**Then** 无会话 token、OTP 或完整 IP 明文（仅摘要）。

---

### User Story 4 - CSRF、重放与猜测不能恢复会话 (Priority: P1)

浏览器状态变更需要 CSRF；重放已撤销 cookie、猜测 token、缓存中断均不能恢复已撤销会话。登录/验证仍受暴力尝试限制（沿用 SF06）。

**Why this priority**: 单会话若可被缓存或重放复活则验收失败。

**Independent Test**: CSRF 缺失/错误被拒；旧 cookie 重放失败；缓存不可用时旧会话仍失败；OTP 暴力限制仍生效。

**Acceptance Scenarios**:

1. **Given** 浏览器写操作无有效 CSRF，**When** 退出或变更会话，**Then** 拒绝且不改变会话世代。
2. **Given** 已撤销 cookie，**When** 在节点切换或缓存重启后重放，**Then** 仍失败，不得签发新会话。
3. **Given** 随机/截断 token，**When** 尝试引导会话，**Then** 失败且不泄露是否曾经有效。

---

### Edge Cases

- 同一账号并发两次登录：仅一个世代胜出，失败者不得拿到对方会话。
- 缓存不可用：不得把已撤销会话当有效；允许短暂走权威存储，失败则关闭为未认证。
- 退出已失效会话：幂等成功，不报错成「仍登录」。
- 代理 Key 请求路径不校验 Web 会话世代。
- 不实现邮件异常登录通知、多会话并存、密码登录。

## Requirements *(mandatory)*

- **FR-001**: 每个普通账户同一时刻 MUST 至多一个有效 Web 会话。
- **FR-002**: 新 Web 登录 MUST 在同一事务撤销旧 Web 会话并提升账户会话世代。
- **FR-003**: 所有 Web 会话校验 MUST 核对当前世代；世代不匹配 MUST 视为未认证。
- **FR-004**: 旧会话在替换完成后 1 秒内 MUST 在所有入口节点失效。
- **FR-005**: Web 会话替换、退出、世代提升 MUST NOT 禁用、轮换或删除任何代理 Key。
- **FR-006**: 用户 MUST 能退出当前 Web 会话；MUST 能结束全部 Web 会话。
- **FR-007**: 状态变更的浏览器请求 MUST 校验 CSRF；失败不得改变会话状态。
- **FR-008**: 会话凭据 MUST 不可预测、可轮换；cookie MUST 为 Secure、HttpOnly、限制站点、带明确过期。
- **FR-009**: 认证事件 MUST 记录结果、设备/IP 摘要与 request ID，MUST NOT 记录 token/OTP。
- **FR-010**: 已登录用户 MUST 能查看当前会话脱敏摘要；匿名 MUST 不能。
- **FR-011**: 缓存或节点异常 MUST NOT 使已撤销会话复活。
- **FR-012**: 登录/验证暴力尝试防护 MUST 保持 SF06 已有限制，本 SF 不放宽。

### Engineering Requirements

- **ER-001 — Contracts**: 版本化会话引导/退出/安全摘要契约；失效码稳定（如 `UNAUTHENTICATED`），不含凭据。
- **ER-002 — Security**: 世代为授权依据之一；cookie 属性门禁；CSRF；负向覆盖 fixation/猜测/重放。
- **ER-003 — Data**: 账户世代与会话行同一权威存储事务；唯一当前有效 Web 会话可验证。
- **ER-004 — Performance**: 替换完成后 1 秒内跨节点拒绝旧会话（实验室双节点或等价时钟测量）。
- **ER-005 — Reliability**: 缓存失败不得复活；权威存储超时则失败关闭为未认证。
- **ER-006 — Observability**: 登录、替换、退出可按 user 与 request ID 查询；无 token。
- **ER-007 — Accessibility**: 账户安全页与退出控件可键盘操作，状态与控件有可感知名称。

### Failure and Recovery

1. **Given** 缓存不可用，**When** 校验已撤销 cookie，**Then** 仍拒绝，不因缓存空而视为有效。
2. **Given** 两请求并发登录同一账号，**When** 均提交成功 OTP，**Then** 仅一代有效会话，另一请求失败或不持有该世代。
3. **Given** 进程重启或节点切换，**When** 重放旧 cookie，**Then** 仍失效。

### Key Entities

- **AccountSessionGeneration**: 账户级单调世代；登录成功与全部退出时提升。
- **WebSession**: 当前唯一有效浏览器会话；绑定世代；摘要可展示，凭据不可读回。
- **AuthSecurityEvent**: 登录/替换/退出结果与 request ID、IP/设备摘要；无 token。

## Success Criteria

- **SC-001**: 两设备先后登录后，当前有效 Web 会话数 = 1，当前世代数 = 1。
- **SC-002**: 第二次登录完成后 1 秒内，旧 cookie 在所有被测节点上的受保护/引导请求成功率 = 0。
- **SC-003**: 会话替换后该账号代理 Key 可用数量不变。
- **SC-004**: 缓存重启、节点切换、旧 cookie 重放的成功引导次数 = 0。
- **SC-005**: CSRF 缺失、token 猜测、会话固定负向用例通过率 100%。
- **SC-006**: 主动退出后旧 cookie 立即失效；审计可按账号与 request ID 命中对应退出事件。

## Assumptions

- 复用 SF06 手机号 OTP、HttpOnly 会话 cookie、CSRF、单会话撤销旧行、OTP 限流。
- 跨节点协调复用 SF03 已落地的分布式状态，不引入新的会话权威库。
- 浏览器矩阵与视觉设计由 SF08 补齐；本 SF 交付安全页数据与可键盘退出/摘要。
- 「异常登录提醒」不含外部消息通道。
