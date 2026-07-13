# Feature Specification: SF16 卖家 Key 周期健康检查与恢复

**Feature ID**: `SF16`  
**Short Name**: `seller-key-health-check`  
**Created**: 2026-07-13  
**Status**: Draft  
**Source**: 周度 Spec F07、PRD 健康监控、Go KeyPool 与并发规范

## 目标与价值

每 30 秒检查所有应参与服务的卖家 Key，依据认证、额度、限流和临时故障更新 health_state；异常 Key 自动退出路由，临时故障恢复后自动回池。检查在后台执行，不阻塞正常代理请求，也不覆盖卖家人工暂停或撤销。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 周期发现失效与零额度 Key (Priority: P1)

作为买家，我希望路由池及时移除已经失效或耗尽的 Key，减少代理失败。

**Independent Test**: 时间可控地运行多个 30 秒周期，注入认证失败、零额度和临时故障，验证状态与路由池。

**Acceptance Scenarios**:

1. **Given** administrative_state=active 的 healthy Key，**When** 到达检查周期，**Then** 调用 SF06 并更新 last_checked_at、额度和结果。
2. **Given** 验证返回余额为零，**When** 检查完成，**Then** health_state=expired，Key 在 1 秒内退出路由。
3. **Given** 验证返回 401/403，**When** 检查完成，**Then** health_state=invalid，Key 立即退出路由。
4. **Given** 临时网络/5xx 连续失败 3 次，**When** 第三次完成，**Then** health_state=down 并从路由池移除。

---

### User Story 2 - 自动恢复临时故障 Key (Priority: P1)

作为卖家，我希望因网络或平台短暂故障下线的 Key 在重新验证成功后自动恢复，无需手工操作。

**Independent Test**: 让 active/down Key 后续检查成功，验证失败计数清零、healthy 恢复和回池。

**Acceptance Scenarios**:

1. **Given** administrative_state=active 且 health_state=down，**When** 后续检查有效、正额度，**Then** 状态恢复 healthy、失败计数清零并重新加入候选池。
2. **Given** administrative_state=paused，**When** 健康调度运行，**Then** 不因成功探测自动改为可路由；恢复由 SF09 驱动。
3. **Given** Key 已 revoked，**When** 调度扫描，**Then** 不读取已擦除凭证、不尝试检查或恢复。

---

### User Story 3 - 正确处理健康检查限流 (Priority: P1)

作为平台，我希望健康探测本身触发 429 时停止频繁探测，并在 30 分钟后恢复检查。

**Acceptance Scenarios**:

1. **Given** 健康检查返回 429，**When** 处理结果，**Then** health_state=rate_limited 并设置 30 分钟 next_check_at。
2. **Given** 30 分钟尚未到期，**When** 调度扫描，**Then** 不主动调用该 Key 的健康接口。
3. **Given** 冷却到期，**When** 再检查成功，**Then** 恢复 healthy 并按资格回池。

### Edge Cases

- 一轮检查耗时超过 30 秒，下一轮又到达。
- 多个调度实例同时检查同一 Key。
- 卖家在检查期间暂停、撤销或恢复 Key。
- 429 Retry-After 长于或短于 30 分钟。
- 检查成功但状态写入/路由失效失败。
- down Key 永远不再被扫描导致无法恢复。
- 大量 Key 同时检查造成上游探测风暴。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 调度 MUST 每 30 秒扫描 administrative_state=active 且到达 next_check_at 的 Key，包括 healthy 和需要恢复探测的 down Key。
- **FR-002**: 每个 Key 同一时间 MUST 最多有一个健康检查；多实例使用租约/锁和幂等运行标识协调。
- **FR-003**: 检查 MUST 使用 SF06 的认证、权限、精确额度和错误分类，单 Key 受 3 秒截止约束。
- **FR-004**: 成功且额度大于零 MUST 设置 healthy、更新额度/last_checked_at、清零连续失败并允许回池。
- **FR-005**: 零额度 MUST 设置 expired；401/403 MUST 设置 invalid；两者立即退出路由。
- **FR-006**: 临时网络、超时或 5xx MUST 增加连续失败计数；前两次保持当前可用状态但标记 warning，第三次设置 down 并退出路由。
- **FR-007**: 任何成功检查 MUST 清零临时失败计数。
- **FR-008**: 429 MUST 设置 rate_limited 和 next_check_at=至少 30 分钟后；更长的可靠 Retry-After 优先。
- **FR-009**: paused 和 revoked Key MUST 不参与周期检查；自动检查 MUST NOT 修改 administrative_state。
- **FR-010**: health_state 变化 MUST 在 1 秒内反映给 SF13；缓存失败时事实状态仍阻止不合格 Key 路由。
- **FR-011**: 健康检查 MUST 后台并发执行且有全局并发上限，不能占用代理请求的关键资源池或阻塞请求处理。
- **FR-012**: 每次检查写入 MUST 幂等并使用状态版本，防止旧结果覆盖更新的人工状态或新检查结果。
- **FR-013**: 检查日志和指标 MUST 只使用脱敏 Key ID，不记录原始凭证或完整响应。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: 调度输入、SF06 结果、健康状态机和 SF13 失效通知须版本化；状态原因与 next_check_at 可查询。
- **ER-002 — Security & Privacy**: 凭证解密只限检查期间；调度权限最小化，结果脱敏，撤销 Key 不得再解密。
- **ER-003 — Data Integrity**: PostgreSQL 保存 health_state、计数、额度、检查时间和版本；分布式锁只协调，不作为事实源。
- **ER-004 — Performance & Capacity**: 一轮应在下个 30 秒周期前完成；并发上限默认 10，可在计划中按官方限制调整且不得影响代理 SLO。
- **ER-005 — Reliability**: 调度支持重启恢复、锁过期、旧结果防覆盖和有界重试；临时失败 3 次才 down。
- **ER-006 — Observability**: 暴露检查总数、耗时、成功率、状态转换、连续失败、跳过、锁竞争、恢复和路由传播延迟。
- **ER-007 — Accessibility**: 后台能力无界面；状态和安全原因通过管理 API 可读，供未来无障碍界面展示。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** 调度进程在持有检查锁时崩溃，**When** 锁超时且下轮开始，**Then** 另一实例安全接管，不重复应用旧结果。
2. **Given** 检查成功但数据库写入失败，**When** 事务回滚，**Then** 保留前状态并记录失败；下轮可重试，不只更新缓存。
3. **Given** 卖家在检查期间撤销 Key，**When** 较晚的 healthy 结果提交，**Then** 版本检查拒绝覆盖 revoked，凭证保持不可路由。

### Key Entities

- **Key Health State**: key_id、health_state、连续失败、精确额度、last_checked_at、next_check_at、原因和版本。
- **Health Check Run**: run_id、key_id、计划/开始/结束时间、结果类别、耗时和状态版本。
- **Check Lease**: 防止同 Key 并发检查的临时协调记录，可过期且非事实源。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% 应检查 Key 在其 30 秒计划周期内开始检查，且一轮不阻塞代理请求。
- **SC-002**: 连续 3 次临时失败后 1 秒内 Key 路由选择次数为 0。
- **SC-003**: 零额度、401/403 状态分类准确率 100%，不会被错误自动恢复。
- **SC-004**: down Key 后续验证成功后一个周期内自动恢复，失败计数清零并按资格回池。
- **SC-005**: 同一 Key 并发检查数始终不超过 1，旧结果覆盖新状态次数为 0。
- **SC-006**: 健康任务运行时代理 P95 与成功率不超过各自 SLO 的允许误差。

## Scope

### In Scope

- 30 秒调度、状态机、连续失败、额度刷新、30 分钟限流冷却、自动恢复和路由传播。

### Out of Scope

- 手工暂停/恢复、外部邮件/微信通知、异常消耗检测、每小时余额页面刷新和多平台。

## Test Requirements

- 时间可控的状态机单元测试覆盖全部结果和恢复。
- 集成测试覆盖分布式锁、数据库版本、缓存失效和进程重启。
- 竞争测试覆盖人工状态与检查结果、多实例调度和旧结果。
- 性能测试验证全量检查不影响代理 SLO。
- 健康领域至少 80% 行覆盖，失败次数、限流和恢复分支直接覆盖。

## Assumptions

- 依赖 SF06、SF08、SF09、SF13。
- 请求级 429 的 30 秒容量 cooldown 属于 SF14；本功能 30 分钟只控制主动健康探测。
- 路线图“每分钟”被更具体周度 Spec 的 30 秒周期替代。

## Traceability

- 周度 Spec：F07-A1 至 F07-A5。
- PRD：4.3.1 AC-3.1.4、4.3.4/健康监控相关要求。
- 规范：`2-Go代理网关开发规范.md` 第 3.2.2、6、7 节；`3-Python后端与数据库设计规范.md` 第 4.3.4。
- 宪章：原则 II、III、V、VI。
