# Feature Specification: SF10 买家代理 Key 签发与撤销

**Feature ID**: `SF10`  
**Short Name**: `proxy-key-lifecycle`  
**Created**: 2026-07-13  
**Status**: Draft  
**Source**: 周度 Spec F09、PRD 4.2.1、代理 Key 与安全规范

## 目标与价值

为已认证买家签发可用于火山方舟代理入口的独立代理 Key，并支持脱敏查询和不可恢复撤销。代理 Key 绑定买家与平台，不绑定单个卖家原始 Key；实际卖家 Key 由 SF13 在每次请求中选择。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 签发代理 Key (Priority: P1)

作为买家，我希望获得唯一的平台代理 Key 和 Base URL，以便像调用官方兼容 API 一样调用 TokenMarket。

**Independent Test**: 买家请求签发火山方舟代理 Key，验证完整值只出现一次、格式正确、校验材料可认证且没有卖家 Key 绑定。

**Acceptance Scenarios**:

1. **Given** 用户已认证且具有买家角色，**When** 请求 `volcano` 代理 Key，**Then** 系统返回 `tmk-{随机标识}` 完整值、key_id、平台和代理 Base URL。
2. **Given** 签发成功，**When** 后续查询 Key 列表，**Then** 只返回名称/脱敏标识、平台、状态和创建时间，不再次返回完整值。
3. **Given** 同一用户多次使用不同幂等键签发，**When** 请求完成，**Then** 每条代理 Key 全局唯一且互不相同。
4. **Given** 相同幂等请求被重放，**When** 再次处理，**Then** 返回同一 key_id；若完整 Key 已在首次响应交付，则重放不得再次回显秘密。

---

### User Story 2 - 撤销泄露或不再使用的代理 Key (Priority: P1)

作为买家，我希望撤销代理 Key 后它立即停止访问，降低凭证泄露风险。

**Independent Test**: 撤销 active Key，验证新认证请求在 1 秒内失败且重复撤销保持幂等。

**Acceptance Scenarios**:

1. **Given** 买家拥有 active 代理 Key，**When** 撤销，**Then** 状态变为 revoked，后续新请求在 1 秒内无法认证。
2. **Given** 代理 Key 属于其他买家，**When** 当前用户尝试撤销，**Then** 操作被拒绝且不泄露 Key 详情。
3. **Given** 代理 Key 已撤销，**When** 再次撤销或尝试恢复，**Then** 重复撤销幂等，恢复被拒绝。

---

### User Story 3 - 防止代理 Key 泄露 (Priority: P1)

作为买家，我希望平台即使数据库被普通读取也不能直接获得可调用的代理 Key。

**Acceptance Scenarios**:

1. **Given** 签发完成，**When** 检查持久记录，**Then** 只存在不可逆校验材料和脱敏后缀，不存在完整 Key 明文。
2. **Given** 日志、错误或审计被查询，**When** 查找 Key 内容，**Then** 最多出现 key_id 或脱敏后缀。

### Edge Cases

- 随机标识碰撞或格式生成失败。
- 数据库提交成功但首次秘密响应丢失。
- 同一幂等键配不同平台或名称。
- 撤销与认证请求并发。
- 用户账户被停用但 Key 状态仍 active。
- 平台值被伪造为 V0.1 不支持的平台。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 签发请求 MUST 从认证上下文确定买家，只接受 platform、可选名称和 idempotency_key；不得接受客户端指定 owner 或卖家 Key。
- **FR-002**: V0.1 platform MUST 只允许 `volcano`。
- **FR-003**: 完整代理 Key MUST 使用 `tmk-` 前缀和至少 128 位不可预测随机熵，且全局唯一。
- **FR-004**: 完整代理 Key MUST 只在首次成功响应中展示一次；持久层只保存不可逆校验材料、脱敏后缀和必要元数据。
- **FR-005**: 代理 Key MUST 绑定 buyer_id 与 platform，MUST NOT 固定绑定 api_key_id 或 seller_id。
- **FR-006**: 成功响应 MUST 返回 key_id、完整 Key、平台、Base URL、状态和创建时间，并明确提示用户安全保存。
- **FR-007**: 后续查询 MUST 仅返回用户自己的 Key，并只展示 key_id、名称、脱敏标识、平台、状态和审计时间。
- **FR-008**: 同一用户 MAY 持有多条代理 Key；不同签发请求必须产生不同秘密。
- **FR-009**: 相同幂等键与请求摘要重放 MUST 返回同一业务结果，但不得在首次交付后重复回显完整秘密。
- **FR-010**: 所有者撤销 MUST 把状态原子切换为 revoked，并在 1 秒内使 SF11 拒绝新请求。
- **FR-011**: revoked 为终态；元数据按审计策略保留，完整秘密和可直接使用的副本不得保留。
- **FR-012**: 签发、撤销、越权和冲突 MUST 写入不含完整 Key 的安全审计。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: 签发、查询和撤销接口须版本化；响应包络用于管理 API，代理 Base URL 指向 SF12/SF15 的公开兼容入口。
- **ER-002 — Security & Privacy**: 高熵生成、哈希校验、一次展示、常量时间比较、服务端所有权、撤销、审计和日志脱敏是发布门槛。
- **ER-003 — Data Integrity**: PostgreSQL 是代理 Key 元数据与状态事实源；唯一、幂等和所有权约束由持久层兜底。
- **ER-004 — Performance & Capacity**: 签发和撤销 P95 小于 500 毫秒；撤销传播到认证层 P95 小于 1 秒。
- **ER-005 — Reliability**: 只有持久提交成功才可交付完整 Key；响应丢失不得通过普通查询恢复秘密，用户可撤销并重新签发。
- **ER-006 — Observability**: 记录签发/撤销结果、耗时、平台、buyer 脱敏 ID 和 request_id；禁止完整 Key、哈希和认证头。
- **ER-007 — Accessibility**: V0.1 无前端；一次展示和不可恢复语义必须通过明确字段/消息表达，供未来界面无障碍提示。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** 随机值碰撞，**When** 唯一约束拒绝写入，**Then** 在有限次数内重新生成；仍失败则整体失败且不返回未提交 Key。
2. **Given** 数据库提交成功但客户端未收到完整 Key，**When** 重放同一请求，**Then** 返回 key_id 和“秘密已交付”状态，不回显完整值；用户可撤销后新建。
3. **Given** 撤销与认证并发，**When** 撤销先提交，**Then** 随后的新认证失败；已开始请求按 SF12/SF15 规则完成或超时。

### Key Entities

- **Proxy Key**: key_id、buyer_id、platform、不可逆校验材料、脱敏后缀、名称、状态、创建/撤销时间、软删除标记和版本。
- **Proxy Key Secret**: 仅首次响应存在的高熵值；不作为可恢复持久数据。
- **Proxy Key Audit Event**: 签发、撤销、拒绝、操作者、脱敏资源、时间和 request_id。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 连续生成 100 万个测试代理 Key 不发生碰撞，格式校验通过率 100%。
- **SC-002**: 持久层、日志、错误和审计扫描中完整代理 Key 出现次数为 0。
- **SC-003**: 撤销后 1 秒内 100% 新认证请求被拒绝。
- **SC-004**: 同一幂等请求重放不产生第二条 Key 记录，也不重复展示完整秘密。
- **SC-005**: 签发与撤销 P95 小于 500 毫秒，越权操作拒绝率 100%。

## Scope

### In Scope

- 火山方舟代理 Key 签发、脱敏查询、不可逆撤销、幂等、所有权和审计。

### Out of Scope

- 暂停/恢复、额度上限、模型白名单、团队余额、固定卖家绑定、调用示例页面和计费。

## Test Requirements

- 随机性、格式、哈希和常量时间校验单元测试。
- 数据库集成测试覆盖唯一、幂等、迁移、撤销和事务。
- 安全测试覆盖日志泄露、枚举、越权、哈希替换和秘密重放。
- 并发测试覆盖碰撞模拟、重复签发与撤销/认证竞争。
- 代理 Key 领域至少 80% 行覆盖，秘密、授权和撤销分支直接覆盖。

## Assumptions

- 依赖 SF04 认证和 SF05 买家授权。
- `tmk-` 后内容的具体编码在计划阶段确定，但随机熵不少于 128 位。
- SF11 负责认证，SF13 负责动态卖家 Key 选择。

## Traceability

- 周度 Spec：F09-A1、F09-A2、F09-A4；F09 固定绑定条款由父索引冲突决策替代。
- PRD：4.2.1 AC-2.1.1 至 AC-2.1.5 中适用于 V0.1 API 的部分。
- 规范：`3-Python后端与数据库设计规范.md` 第 4.2.3、4.3、4.5、6、7 节。
- 宪章：原则 II、III、V、VI。
