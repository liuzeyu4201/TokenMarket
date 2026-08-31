# Feature Specification: 异步结算、对账、冲正与未决处理

**Feature Branch**: `047-async-settlement-recon`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 异步结算、对账、冲正与未决处理"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF29-异步结算对账冲正与未决处理.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 长期未决能否归零？ → A: 不能。保持 unresolved，记录责任人。
- Q: 迟到 reported cost？ → A: 优先按 reported 结算；若已按 usage 暂算，只追加差额/冲正，不覆盖原分录。
- Q: 重复/乱序事件？ → A: 幂等；最终结果确定，不重复入账。
- Q: 人工冲正？ → A: 需 RBAC、step-up、理由与预览；原分录仍在。
- Q: 专享更换后的异步任务？ → A: 仍用原资源亲和与原价格版本。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 迟到与乱序事件 (Priority: P1)

回调、usage、reported cost 可迟到或乱序，最终只结算一次。

**Independent Test**: 同一 request 重复/乱序投递 10 次，净入账一组。

**Acceptance Scenarios**:

1. **Given** 已 usage 暂算，**When** 迟到 reported 到达且金额不同，**Then** 追加差额分录，原分录仍在。
2. **Given** 同一 event_id 重复，**When** 再投递，**Then** 无第二组 settled。
3. **Given** reported 先于 usage，**When** 后到 usage，**Then** 不重复扣减。

---

### User Story 2 - 未决原因与自动恢复 (Priority: P1)

金额缺失、usage 缺失、解析失败、异步未完成进入对应 unresolved；可恢复则在 SLA 内结算。

**Independent Test**: 四种缺陷各产生正确 reason_code；补齐证据后 tick 结算。

**Acceptance Scenarios**:

1. **Given** 解析失败，**When** 入队，**Then** reason=`PARSE_FAILED`，金额暴露为预留额而非 0。
2. **Given** 未决后证据到达，**When** worker tick，**Then** 用原 rate_version 结算并关闭 case。
3. **Given** SLA 到期仍无证据，**When** tick，**Then** 保持 unresolved，更新责任人时间，不得释放为 0。

---

### User Story 3 - 对账、差异与人工冲正 (Priority: P1)

自动对账出工单；人工冲正需预览与 step-up。

**Independent Test**: 超阈值差异产生工单；无 step-up 的冲正次数 = 0。

**Acceptance Scenarios**:

1. **Given** reported 与 computed 差超阈值，**When** 入账，**Then** 产生可下钻 VARIANCE 工单。
2. **Given** 每日对账，**When** 运行，**Then** 账本平衡、无孤儿 reservation、聚合=明细。
3. **Given** 未 step-up，**When** 冲正，**Then** 拒绝；确认后原分录仍在且净余额正确。

---

### Edge Cases

- 不得静默归零。
- 不得删除错误分录。
- 异步任务跨专享更换仍锁定原 connection 与价格版本。

## Requirements *(mandatory)*

- **FR-001**: 对账 worker MUST 幂等、可重试、可限速。
- **FR-002**: unresolved MUST 记录原因码、缺失证据、金额暴露、下次动作、重试时间、责任人/SLA。
- **FR-003**: reported 到达 MUST 优先；已 usage 暂算 MUST 追加差额/冲正。
- **FR-004**: 自动对账 MUST 比较 reservation、usage、ledger 与证据并产生差异工单。
- **FR-005**: 人工冲正 MUST 要求 RBAC、step-up、理由、预览与审计。
- **FR-006**: MUST NOT 把长期未决记 0 或删除分录。
- **FR-007**: 异步恢复 MUST 使用原价格版本与资源亲和。

### Engineering Requirements

- **ER-001**: 扩展 `ledger/v1` 1.2.0（unresolved case、recon ticket）。
- **ER-002**: `app/domain/recon` worker + 内部 HTTP。
- **ER-003**: 覆盖率 ≥80%；乱序、未决、冲正、每日对账测试。

## Success Criteria

- **SC-001**: 重复/乱序导致重复结算次数 = 0。
- **SC-002**: 四类缺陷 reason_code 正确率 100%。
- **SC-003**: 超阈值差异未出工单次数 = 0。
- **SC-004**: 无 step-up 冲正成功次数 = 0。
- **SC-005**: 冲正后原分录缺失次数 = 0。

## Assumptions

- 管理员 UI 在 SF31；本 SF 提供内部 API 与审计。
- 真实厂商账单拉取属外部阻塞，本 SF 用注入证据事件。
