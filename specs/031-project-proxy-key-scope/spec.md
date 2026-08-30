# Feature Specification: Project 代理 Key 与权限范围

**Feature Branch**: `031-project-proxy-key-scope`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 Project 代理 Key 与权限范围"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF12-Project代理Key与权限范围.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: Key 与 Project 关系？ → A: 新签发的 V0.2 Key 必须固定归属一个 Project。权限是 Project/Binding 能力的子集。历史 volcano 无 Project Key 保留，不用于三协议数据面。
- Q: 明文与轮换？ → A: 创建与轮换各只回显一次明文。服务端只存 HMAC。已撤销不可恢复。禁用可再启用；撤销只能新建。
- Q: 限制如何组合？ → A: 协议、模型、CIDR、周期额度、过期同时生效，取最严格交集。
- Q: 失败是否区分不存在？ → A: 否。鉴权失败对外同一结果，不暴露 Key 是否存在。比较抗时序泄漏。
- Q: 撤销传播？ → A: 直读事实源，网关正向缓存 TTL ≤1s。已建立流不得凭已撤销 Key 开始新请求。
- Q: Web 会话？ → A: 单会话替换不影响代理 Key。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 为 Project 签发一次性明文 Key (Priority: P1)

买家在买家工作区为已有 Binding 的协议签发代理 Key，明文只出现一次。

**Why this priority**: Key 是数据面鉴权根。

**Independent Test**: 创建回显 secret；列表与再次 GET 无完整明文；库中无明文。

**Acceptance Scenarios**:

1. **Given** Project 已发布对应协议 Binding，**When** 签发带名称与协议集合的 Key，**Then** 201 含一次性 secret 与安全前后缀。
2. **Given** 刚创建的 Key，**When** 列表或幂等重放，**Then** 无完整 secret。
3. **Given** 协议不在 Project/Binding 能力内，**When** 签发，**Then** 拒绝。

---

### User Story 2 - 协议/模型/IP/额度/过期限制 (Priority: P1)

Key 可收窄协议、模型 allowlist、CIDR、周期额度和过期时间；组合取交集。

**Why this priority**: 防止 Key 越权使用 Binding。

**Independent Test**: 五项限制各自允许/拒绝；同时收紧时以最严者为准。

**Acceptance Scenarios**:

1. **Given** 仅允许 openai 的 Key，**When** 以 anthropic 鉴权，**Then** 失败且不泄漏。
2. **Given** 模型/CIDR/过期不匹配，**When** 鉴权，**Then** 失败。
3. **Given** 周期额度 N，**When** 并发 N+k 次到达边界，**Then** 接受次数恰好 N。

---

### User Story 3 - 轮换、禁用、撤销 (Priority: P1)

轮换签发新秘密并使旧秘密立即失效。禁用可恢复。撤销不可恢复，1 秒内所有入口拒绝。

**Why this priority**: 泄漏响应与生命周期。

**Independent Test**: 轮换后旧 secret 失败；撤销后 1s 内鉴权失败；撤销后再启用失败。

**Acceptance Scenarios**:

1. **Given** 有效 Key，**When** 轮换，**Then** 新 secret 一次回显，旧 secret 失败。
2. **Given** 撤销，**When** 1 秒内鉴权，**Then** 失败。
3. **Given** 已撤销，**When** 启用，**Then** 拒绝。

---

### User Story 4 - 列表、审计与买家 UI (Priority: P2)

列表与审计只显示前后缀。跨 Project 使用或猜 key ID 不泄漏。UI 可签发并看到安全掩码。

**Why this priority**: 防枚举与误用明文。

**Independent Test**: 他 Project 的 Key 操作 404 同形；列表无 tmk- 后完整 hex。

**Acceptance Scenarios**:

1. **Given** 两 Project，**When** A 对 B 的 key_id 撤销/轮换，**Then** 与未知 ID 同形 404。
2. **Given** 列表，**When** 检查字段，**Then** 仅前后缀与元数据。
3. **Given** 买家工作区，**When** 打开 Project 的 Key 区，**Then** 可签发；卖家工作区 403。

---

### Edge Cases

- 空协议列表、非法 CIDR、额度为 0 或负 → 校验失败。
- 归档 Project 拒绝新 Key。
- Key 不能换取 Connection 明文。
- 日志/错误不含 secret。
- volcano 历史签发路径保持，不要求 Project。

## Requirements *(mandatory)*

- **FR-001**: V0.2 Key MUST 归属一个 Project；权限 MUST 为 Project/Binding 子集。
- **FR-002**: MUST 支持名称、协议集合、模型 allowlist、CIDR、周期额度、过期、状态。
- **FR-003**: 明文 MUST 仅在创建/轮换响应出现一次；存储 MUST 为不可逆 HMAC。
- **FR-004**: 列表/审计 MUST 仅安全前后缀。
- **FR-005**: 鉴权比较 MUST 抗时序泄漏；失败 MUST 不暴露存在性。
- **FR-006**: 代理记录 MUST 含 key ID、MUST NOT 含明文。
- **FR-007**: Web 会话变化 MUST NOT 改变 Key 生命周期。
- **FR-008**: 撤销 MUST ≤1s 全局生效；已撤销不可恢复。
- **FR-009**: 周期额度并发到达边界时已接受请求数 MUST = 限额。
- **FR-010**: 跨 Project 操作 MUST 同形 404。
- **FR-011**: Key MUST NOT 作为 upstream credential 或换取连接密钥。

### Engineering Requirements

- **ER-001**: 扩展代理 Key 契约/OpenAPI（Project 作用域）。
- **ER-002**: CSRF 写操作；工作区透镜。
- **ER-003**: Postgres 为鉴权 SoR；配额原子递增。
- **ER-004**: 网关正向缓存 TTL ≤1s。
- **ER-005**: 领域覆盖率 ≥80%。

## Success Criteria

- **SC-001**: 创建后在库/日志/响应列表中完整明文出现次数 = 0（除当次创建/轮换体）。
- **SC-002**: 五项限制正/负向测试通过率 100%。
- **SC-003**: 并发额度超发已接受次数 = 0。
- **SC-004**: 撤销后 1 秒内鉴权成功次数 = 0。
- **SC-005**: 跨 Project 与未知 ID 的 code 一致。
- **SC-006**: 列表无法用于认证（仅掩码）。

## Assumptions

- 测试额度扣减与账本在 SF13/SF28；本 SF 周期额度为 Key 级请求次数上限。
- Gateway 继续 HMAC 查找；本 SF 扩展查找结果与限制检查。
- 流的中途切断由网关后续 SF 在每次新请求鉴权时 fail-closed。
