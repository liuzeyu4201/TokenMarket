# Feature Specification: SF08 卖家 API Key 接入

**Feature ID**: `SF08`  
**Short Name**: `seller-key-onboarding`  
**Created**: 2026-07-13  
**Status**: Draft  
**Source**: 周度 Spec F03、PRD 4.1.1、Python 数据库规范、宪章敏感凭证要求

## 目标与价值

允许已认证卖家将有效且有剩余额度的火山方舟 API Key 安全接入 TokenMarket。系统在验证成功后才保存凭证，完整值采用认证加密且不再回显，为后续生命周期管理、健康检查和路由建立可信 Key 记录。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 安全接入有效 Key (Priority: P1)

作为卖家，我希望提交火山方舟 Key 后快速知道验证结果，并在成功时看到脱敏标识和当前额度。

**Independent Test**: 以卖家身份提交受控有效凭证，验证先执行 SF06、后创建一条加密记录，响应不包含完整值。

**Acceptance Scenarios**:

1. **Given** 用户已认证且具有卖家角色，Key 有效且额度大于零，**When** 提交接入，**Then** 系统在验证成功后保存一条 Key 记录并返回 key_id、平台、脱敏标识、额度、状态和验证时间。
2. **Given** 相同幂等键和相同请求重放，**When** 再次处理，**Then** 返回首次 key_id，不重复验证或创建记录。
3. **Given** 同一卖家接入多条不同有效 Key，**When** 请求分别完成，**Then** 每条拥有不同 key_id，均归属于当前卖家。

---

### User Story 2 - 拒绝无效、零额度和重复 Key (Priority: P1)

作为卖家，我希望错误原因足够可操作，同时平台不会保存不可用或重复的凭证。

**Independent Test**: 提交认证失败、权限失败、零额度、限流、临时故障和已接入凭证，检查持久记录数不增加。

**Acceptance Scenarios**:

1. **Given** Key 认证失败、权限不足或额度为零，**When** 接入，**Then** 返回对应安全错误且不保存任何可解密凭证。
2. **Given** SF06 返回限流或临时故障，**When** 接入，**Then** 返回可重试结果，不把 Key 标记为无效，也不创建正式记录。
3. **Given** 同一火山方舟 Key 已由任一账户接入，**When** 再次提交，**Then** 系统拒绝重复接入，但不向调用方泄露原所有者。

---

### User Story 3 - 防止凭证在处理链路泄露 (Priority: P1)

作为卖家，我希望原始 Key 只在验证和加密所需的极短时间内出现，任何错误、日志或后续查询都不能恢复展示完整值。

**Acceptance Scenarios**:

1. **Given** 接入成功，**When** 查看响应、日志、追踪和数据库普通查询，**Then** 看不到原始 Key 明文。
2. **Given** 加密或数据库写入失败，**When** 请求结束，**Then** 不存在部分 Key 记录、未加密副本或带凭证错误。

### Edge Cases

- 同一凭证以不同大小写、空白或前缀格式提交。
- 同一 Key 被同一或不同卖家并发接入。
- 验证成功后、加密前密钥服务不可用。
- 加密成功后数据库事务失败。
- 数据库提交成功但响应丢失，客户端重试。
- 密钥版本轮换期间新旧写入并发。
- 响应或异常对象意外携带 Authorization 头。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 接入请求 MUST 从认证会话确定卖家身份，接受 platform、api_key 和 idempotency_key；V0.1 platform 只允许 `volcano`。
- **FR-002**: 接入 MUST 先调用 SF06；仅 valid、具备权限且 remaining_quota > 0 的结果可以进入持久化阶段。
- **FR-003**: 系统 MUST 为原始 Key 计算不可逆、带服务端秘密材料的去重指纹；同一凭证在平台范围内不得重复接入。
- **FR-004**: 原始 Key MUST 使用认证加密保存，持久记录包含密文、随机 nonce、认证标签和外部密钥版本，不保存明文字段。
- **FR-005**: 加密密钥材料 MUST 从批准的外部配置或秘密提供方注入，不得与密文存储在同一数据记录或提交到仓库。
- **FR-006**: 原始 Key 明文 MUST 只在验证和加密期间存在，目标是在服务器内存中停留不超过 5 秒，并在所有可控缓冲区尽快释放。
- **FR-007**: 成功记录 MUST 包含 UUID key_id、seller_id、platform、脱敏标识、精确额度及单位、administrative_state、health_state、last_validated_at、审计时间、软删除标记和版本。
- **FR-008**: 接入后的默认 administrative_state MUST 为 active；初始 health_state 来自本次可信验证。
- **FR-009**: 成功响应 MUST 只返回 key_id、脱敏 Key、平台、精确额度、状态和验证时间，不得再次返回完整 Key。
- **FR-010**: 相同幂等键和请求摘要重放 MUST 返回首次结果；相同幂等键配不同凭证摘要 MUST 返回冲突。
- **FR-011**: 不同 Key 的合法接入数量在 V0.1 不设业务上限，但必须受请求频率与并发保护。
- **FR-012**: 任何验证、加密、持久化或审计失败 MUST NOT 留下可被路由使用的半完成 Key。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: 接入接口须版本化并纳入 OpenAPI；错误区分 unsupported_platform、invalid_key、forbidden、zero_quota、rate_limited、temporary_unavailable、duplicate 和 encryption_failure。
- **ER-002 — Security & Privacy**: 原始 Key 为高价值可逆秘密；需要认证加密、外部版本化密钥、最小内存驻留、统一脱敏、服务端卖家授权、审计和秘密扫描。
- **ER-003 — Data Integrity**: PostgreSQL 是 Key 元数据事实源；去重、所有权、状态和幂等约束由数据库兜底，额度采用精确数值并携带单位。
- **ER-004 — Performance & Capacity**: 不含上游验证的加密与持久化 P95 小于 300 毫秒；含验证的正常接入在 3.5 秒内完成。
- **ER-005 — Reliability**: 验证、加密、写入和审计必须形成明确提交边界；不得自动重放包含敏感写入的非幂等步骤。
- **ER-006 — Observability**: 记录平台、卖家脱敏 ID、结果类别、验证/加密/写入耗时和 request_id；严禁原始 Key、密文、nonce、tag 或认证头。
- **ER-007 — Accessibility**: V0.1 无前端；响应必须提供机器可读错误类别和不泄密的修复建议。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** 验证成功但加密服务不可用，**When** 接入继续，**Then** 整体失败、不写入 Key，故障可观测且客户端可用同一幂等键重试。
2. **Given** 加密成功但数据库提交失败，**When** 事务回滚，**Then** 不留下密文孤儿、路由缓存或成功审计。
3. **Given** 数据库已提交但响应中断，**When** 客户端以相同幂等键重试，**Then** 返回原 key_id 且不再次创建或覆盖密文。

### Key Entities

- **Seller API Key**: 卖家拥有的火山方舟凭证元数据与认证密文；事实源为 PostgreSQL，密文为 restricted secret，状态和所有权可审计。
- **Credential Fingerprint**: 用于同平台去重的不可逆值；不得用于恢复原 Key，也不得在外部响应中返回。
- **Encryption Metadata**: nonce、认证标签和密钥版本；与密文一起保证完整性，但不包含实际密钥材料。
- **Onboarding Idempotency Record**: 幂等键、敏感请求的安全摘要、结果 key_id 和状态。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% 有效且正额度凭证成功创建一条可解密验证的记录，无效/零额度/临时失败创建记录数为零。
- **SC-002**: 同一凭证 100 个并发接入请求最多创建一条 Key 记录。
- **SC-003**: 相同幂等请求重放 10 次返回同一 key_id，验证和持久化副作用不重复。
- **SC-004**: 含正常验证的接入 P95 小于 3.5 秒。
- **SC-005**: 响应、日志、追踪、数据库导出和测试产物扫描不出现完整原始 Key。
- **SC-006**: 密文、nonce、tag 或密钥版本任一被篡改时，后续解密验证 100% 失败关闭。

## Scope

### In Scope

- 火山方舟 Key 接入授权、验证、去重、认证加密、持久化、脱敏响应和幂等。

### Out of Scope

- 暂停/恢复/撤销、周期健康检查、批量 CSV、保留额度、挂售价格、前端和多平台。

## Test Requirements

- 单元测试覆盖验证结果门槛、脱敏、指纹、状态初始化和错误映射。
- 集成测试使用真实数据库验证迁移、约束、事务和回退。
- 安全测试覆盖密文篡改、密钥缺失/轮换、日志泄露和越权。
- 并发与幂等测试覆盖同 Key、同指纹和响应丢失重试。
- Key 领域包至少 80% 行覆盖，凭证、授权、迁移和并发分支直接覆盖。

## Assumptions

- 依赖 SF04 认证、SF05 卖家授权、SF06 火山方舟验证。
- 认证加密算法和秘密提供方在计划阶段选定，但不得弱于宪章要求；HSM 不是 V0.1 强制依赖。
- Key 加入实际路由候选由 SF13 负责。

## Traceability

- 周度 Spec：F03-A1、F03-A2、F03-A3。
- PRD：4.1.1 AC-1.1.2 至 AC-1.1.5。
- 规范：`3-Python后端与数据库设计规范.md` 第 4.1、4.2.2、4.3、4.5、6、7 节。
- 宪章：原则 II、III、V、VI。
