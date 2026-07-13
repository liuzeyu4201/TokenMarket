# Feature Specification: SF11 代理 Key 认证

**Feature ID**: `SF11`  
**Short Name**: `proxy-key-authentication`  
**Created**: 2026-07-13  
**Status**: Draft  
**Source**: 周度 Spec F04/F09、Go 网关流水线与错误处理规范

## 目标与价值

在代理网关入口认证买家代理 Key，建立可信的 buyer、platform、proxy_key_id 和会话状态上下文，供授权、路由、计量与日志使用。所有无效凭证对外采用一致结果，避免 Key 枚举。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 使用有效代理 Key 建立调用上下文 (Priority: P1)

作为买家，我希望携带有效代理 Key 的请求被快速识别，并准确使用该 Key 所属平台与账户权限。

**Independent Test**: 使用 SF10 创建的 active Key 调用认证入口，验证返回内部上下文且不暴露校验材料。

**Acceptance Scenarios**:

1. **Given** Authorization 为 `Bearer {active_proxy_key}`，**When** 请求到达匹配平台的代理入口，**Then** 认证通过并建立 key_id、buyer_id、platform 和状态上下文。
2. **Given** 客户端同时提供伪造 buyer_id 或 platform 头，**When** 认证完成，**Then** 下游只使用代理 Key 记录中的事实。
3. **Given** 客户端提供 X-Request-ID，**When** 格式合法且无冲突，**Then** 认证日志关联该请求标识；否则网关生成新的安全标识。

---

### User Story 2 - 一致拒绝无效代理 Key (Priority: P1)

作为平台，我希望缺失、格式错误、未知、已撤销、账户停用或平台不匹配的凭证都无法进入路由阶段。

**Independent Test**: 表驱动覆盖所有无效状态，验证均在路由和上游调用前结束。

**Acceptance Scenarios**:

1. **Given** Authorization 缺失或不符合 Bearer 结构，**When** 认证，**Then** 返回 401 的统一安全错误。
2. **Given** Key 未知、已撤销或所属账户不可用，**When** 认证，**Then** 返回相同外部错误语义，不披露具体存在状态。
3. **Given** Key 属于火山方舟但用于其他平台路径，**When** 认证，**Then** 返回 401/403 契约规定结果且不进入路由。

---

### User Story 3 - 快速响应撤销 (Priority: P1)

作为买家，我希望代理 Key 被撤销后立刻停止新调用，即使认证缓存中曾存在有效记录。

**Acceptance Scenarios**:

1. **Given** active Key 刚被撤销，**When** 1 秒后发起新请求，**Then** 认证失败。
2. **Given** 认证缓存不可用，**When** 请求到达，**Then** 回源事实库或失败关闭，不默认允许。

### Edge Cases

- Authorization 含多个值、额外空格、超长输入或非法编码。
- Key 前缀合法但随机部分长度错误。
- 哈希查询命中但记录处于软删除、撤销或账户停用状态。
- 撤销和认证在不同节点并发。
- 缓存返回旧版本记录或遭遇穿透攻击。
- 大量随机 Key 猜测造成数据库压力。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 认证 MUST 只接受单个标准 Bearer 凭证，缺失、重复、超长或格式错误均在解析阶段拒绝。
- **FR-002**: 系统 MUST 对完整 Key 计算既定不可逆校验值，以常量时间方式验证，不保存或记录完整输入。
- **FR-003**: 认证通过 MUST 同时满足 Key 存在、status=active、未软删除、平台与路径一致、owner 账户 active 且具备买家角色。
- **FR-004**: 下游认证上下文 MUST 包含 request_id、proxy_key_id、buyer_id、platform、Key 状态版本和安全脱敏标识。
- **FR-005**: 客户端提供的用户、角色、平台和 Key ID 字段 MUST NOT 覆盖认证上下文。
- **FR-006**: 未知、撤销、停用和所有者不可用对外 MUST 使用不支持枚举的统一 401 错误；内部保留脱敏原因分类。
- **FR-007**: 平台不匹配 MUST 在上游选择前失败，具体使用 401 或 403 必须在公开契约中固定。
- **FR-008**: SF10 撤销后的新请求 MUST 在 1 秒内失效，缓存必须按版本或主动失效更新。
- **FR-009**: 认证缓存只能加速可重建记录；缓存不可用或不可信时 MUST 回源，无法确认则失败关闭。
- **FR-010**: 系统 MUST 限制失败认证速率并防止随机 Key 枚举拖垮持久层。
- **FR-011**: 完整 Key、哈希、Authorization 头 MUST NOT 出现在日志、错误、指标、追踪或 panic 输出中。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: 代理认证是公开 OpenAI-compatible 路径的前置契约；失败使用统一错误结构、HTTP 401 和 request_id，不返回上游格式。
- **ER-002 — Security & Privacy**: 常量时间校验、默认拒绝、撤销、速率限制、缓存失败关闭、凭证脱敏和账户状态校验为强制要求。
- **ER-003 — Data Integrity**: PostgreSQL 是 Key/账户状态事实源；缓存条目包含版本和有限 TTL，不得让已撤销状态回滚。
- **ER-004 — Performance & Capacity**: 缓存命中认证 P95 小于 5 毫秒，事实源回查 P95 小于 30 毫秒；需支持 V0.1 超过 100 QPS 压测目标。
- **ER-005 — Reliability**: 数据源超时采用有界等待且不自动放行；进程重启后可从事实源重建缓存。
- **ER-006 — Observability**: 记录认证成功率、失败类别、缓存命中、回源耗时和限流计数，只使用脱敏 Key ID 与 request_id。
- **ER-007 — Accessibility**: V0.1 无前端；错误需包含稳定代码与 request_id，支持开发者定位但不泄露状态细节。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** 缓存命中旧 active 记录但事实已 revoked，**When** 版本失效传播，**Then** 1 秒内停止命中；无法确认版本时失败关闭。
2. **Given** 数据库或缓存同时不可用，**When** 认证请求到达，**Then** 返回暂时不可认证，不进入路由或上游调用。
3. **Given** 恶意随机 Key 洪泛，**When** 失败速率超过阈值，**Then** 在事实库查询前限流并产生安全告警信号。

### Key Entities

- **Proxy Authentication Record**: proxy_key_id、校验材料、buyer_id、platform、状态、版本和账户状态引用。
- **Authenticated Proxy Context**: 单次请求的可信身份与平台上下文，不持久化完整凭证。
- **Authentication Security Event**: 脱敏 Key 标识、结果类别、来源摘要、时间和 request_id。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 全部有效状态测试认证成功率 100%，全部无效状态在路由前拒绝率 100%。
- **SC-002**: 撤销后 1 秒内新请求通过次数为 0。
- **SC-003**: 缓存命中认证 P95 小于 5 毫秒，100 QPS 压测下无错误率显著上升。
- **SC-004**: 随机 Key、未知 Key、撤销 Key 的外部错误内容不可区分账户存在性。
- **SC-005**: 日志、错误、追踪和测试输出中完整代理 Key 与 Authorization 头出现次数为 0。

## Scope

### In Scope

- Bearer 解析、Key 校验、状态/平台/账户检查、认证上下文、缓存失效和失败限流。

### Out of Scope

- 卖家 Key 解密、路由、上游转发、用户会话认证、计量和买家配额。

## Test Requirements

- 表驱动单元测试覆盖所有解析和状态组合。
- 集成测试覆盖事实库、缓存重建、撤销传播和账户停用。
- 安全测试覆盖枚举、计时差异、凭证泄露、超长头和洪泛。
- 负载测试覆盖 100 QPS 以上认证和缓存降级。
- 网关认证包至少 80% 行覆盖，拒绝和失败关闭分支直接覆盖。

## Assumptions

- 依赖 SF10 的代理 Key 记录和撤销状态。
- SF05 定义角色含义，SF13 消费认证上下文中的 buyer_id/platform。
- 公开路径仅支持 HTTPS 的生产部署；本地隔离环境可使用 HTTP。

## Traceability

- 周度 Spec：F04-A3、F09-A3。
- 规范：`2-Go代理网关开发规范.md` 第 3.1 Auth、4.1、5、6、7 节。
- 宪章：原则 I、II、V、VI。
