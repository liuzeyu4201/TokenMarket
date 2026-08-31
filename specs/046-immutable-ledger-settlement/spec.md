# Feature Specification: 测试额度预留、同步结算与不可变账本

**Feature Branch**: `046-immutable-ledger-settlement`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 测试额度预留、同步结算与不可变账本"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF28-测试额度预留同步结算与不可变账本.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 能否充值/提现/转让？ → A: 不能。仅内部种子发放测试额度。
- Q: 未知成本？ → A: 不得释放 reservation，转入 unresolved，不得记 0。
- Q: 修账？ → A: 禁止 UPDATE/DELETE 已发布分录；冲正只追加相反分录。
- Q: 余额？ → A: 在线投影；失败则从全量分录重建，禁止直接改余额修数。
- Q: 幂等？ → A: 同一 request/idempotency key 只产生一组业务效果。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 原子预留 (Priority: P1)

请求前按账户、Project、Key 可用测试额度原子预留。

**Independent Test**: 100 并发争最后额度，accepted 总额 ≤ 可用额。

**Acceptance Scenarios**:

1. **Given** 可用额 1000，**When** 100 个并发各预留 50，**Then** 成功预留合计 ≤ 1000。
2. **Given** 同一 idempotency/request，**When** 重试 10 次，**Then** 只扣一次。
3. **Given** 任一桶不足，**When** 预留，**Then** 拒绝且不写入部分扣减。

---

### User Story 2 - 同步结算与平衡分录 (Priority: P1)

已知成本时同一事务消费 reservation、写平衡分录并释放余量。

**Independent Test**: buyer debit = seller earning + spread；余量释放后可用额正确。

**Acceptance Scenarios**:

1. **Given** 预留 100、结算 80/64/16，**When** 结算完成，**Then** 三方平衡且余量 20 释放。
2. **Given** 平台拒绝且未产生 upstream 成本，**When** 释放，**Then** 可用额恢复。
3. **Given** 成本未知，**When** 结束，**Then** reservation 保持未决，不释放。

---

### User Story 3 - 不可变与可重建 (Priority: P1)

分录只追加；投影可从分录重建。

**Independent Test**: 修改/删除已发布分录被约束拒绝；重建余额 = 在线投影。

**Acceptance Scenarios**:

1. **Given** 已发布分录，**When** 尝试 UPDATE/DELETE，**Then** 失败。
2. **Given** 任意结算后，**When** 从全量分录重建，**Then** 与投影精确一致。
3. **Given** 冲正，**When** 完成，**Then** 原分录仍在，仅新增相反分录。

---

### Edge Cases

- 无充值、提现、法币锚定接口。
- 预留后进程退出：恢复时 reservation 仍占用，不得重复扣。
- 结算重试不得重复入账。

## Requirements *(mandatory)*

- **FR-001**: reservation MUST 以 request/idempotency key 唯一，并同时检查账户/Project/Key 额度。
- **FR-002**: 已知成本 MUST 在同一事务结算平衡分录并释放余量。
- **FR-003**: 分录 MUST 只追加，含账户、方向、金额、单位、request、价格版本与证据引用。
- **FR-004**: 在线余额 MUST 可从分录重建，禁止直接 UPDATE 修余额。
- **FR-005**: 平台拒绝或确认无 upstream 成本 MUST 释放 reservation。
- **FR-006**: 成本不确定 MUST 进入 unresolved，不得释放、不得记 0。
- **FR-007**: 冲正 MUST 只追加相反分录。
- **FR-008**: MUST NOT 提供充值、提现、转让或法币锚定。

### Engineering Requirements

- **ER-001**: 扩展 `ledger/v1` 至 1.1.0。
- **ER-002**: Billing `app/domain/ledger` + 内部 HTTP；库约束阻止改删分录。
- **ER-003**: 覆盖率 ≥80%；并发、幂等、平衡、重建、负向改删测试。

## Success Criteria

- **SC-001**: 并发 accepted 预留合计 ≤ 可用额。
- **SC-002**: 同一 key 重试业务效果组数 = 1。
- **SC-003**: 已结算事务不平衡次数 = 0。
- **SC-004**: 重建与投影不一致次数 = 0。
- **SC-005**: 已发布分录被改删成功次数 = 0。

## Assumptions

- 测试额度种子发放不是充值产品；SF13 再做买家可见预算 UI。
- 异步迟到账单属 SF29；本 SF 只同步路径与 unresolved 占位。
