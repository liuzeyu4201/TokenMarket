# Feature Specification: Project 预算、测试额度、用量与开发者引导

**Feature Branch**: `048-project-budget-guide`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 Project 预算、测试额度、用量与开发者引导"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF13-Project预算测试额度用量与开发者引导.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 充值/提现/法币？ → A: 不提供任何入口或文案暗示可购买、可提现、与人民币 1:1。
- Q: 余额来源？ → A: 只读 SF28/SF29 不可变账本投影；页面与账本抽样一致。
- Q: 硬阈值？ → A: 并发下不得接受超过可用额度（账本可用与硬预算的较小值）的新 reservation。
- Q: 未决？ → A: 展示原因与后续动作，不得显示为 0 成本。
- Q: 示例？ → A: 三协议各自原生 curl/SDK，无跨协议转换。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 首条原生请求引导 (Priority: P1)

买家按 checklist 完成 Binding、Key、示例调用与结果解释。

**Independent Test**: checklist 四步可勾选；三协议示例字段原生且互异。

**Acceptance Scenarios**:

1. **Given** 新 Project，**When** 打开引导，**Then** 看到 Binding → Key → 测试调用 → 结果解释。
2. **Given** openai/anthropic/vertex，**When** 查看示例，**Then** 鉴权头与路径各为原生，无统一转换层。
3. **Given** 已发布 Binding 且已签发 Key，**When** 刷新，**Then** 对应步骤为已完成。

---

### User Story 2 - 测试额度总览与硬阈值 (Priority: P1)

总览 available/reserved/settled/unresolved；软阈值告警，硬阈值拒绝。

**Independent Test**: 并发 admit 总额 ≤ min(账本可用, 硬预算)；unresolved 行金额 ≠ 0。

**Acceptance Scenarios**:

1. **Given** 账本投影，**When** 打开总览，**Then** 四字段与账本一致。
2. **Given** 达到软阈值，**When** 查询预算，**Then** 告警仍可预留。
3. **Given** 硬阈值或账本不足，**When** 并发预留，**Then** 超额请求被拒绝。

---

### User Story 3 - 用量下钻与文案边界 (Priority: P1)

用量可筛选并下钻 request_id；全站无充值提现误导。

**Independent Test**: 导出含 request_id；源码/UI 扫描无充值支付提现入口。

**Acceptance Scenarios**:

1. **Given** 多笔 reservation，**When** 按 Key/结算状态筛选，**Then** 行含 request_id。
2. **Given** unresolved 行，**When** 展示，**Then** 有原因且金额不是 0。
3. **Given** 产品文案，**When** 扫描，**Then** 无充值按钮、支付链接或法币锚定。

---

### Edge Cases

- 预算不是最终上限：必须说明 reservation 与异步调整。
- 无 Binding/Key 时 checklist 未完成，示例仍只读可见。

## Requirements *(mandatory)*

- **FR-001**: MUST 支持 Project 总预算与可选 Key 子预算；软告警、硬拒绝。
- **FR-002**: 总览 MUST 展示 available、reserved、settled、unresolved，未决不得当免费。
- **FR-003**: MUST 按三协议生成原生 curl/SDK 示例。
- **FR-004**: 用量 MUST 可按 Key 与结算状态筛选并下钻 request_id。
- **FR-005**: 首次 checklist MUST 覆盖 Binding、Key、测试调用、结果解释。
- **FR-006**: MUST NOT 提供充值、提现、支付或法币锚定。
- **FR-007**: 页面聚合 MUST 与账本投影一致。

### Engineering Requirements

- **ER-001**: 扩展 `project/v1` 1.2.0（budget/guide/usage）。
- **ER-002**: Billing `project_overview` 复用账本；API `BudgetService`。
- **ER-003**: 覆盖率 ≥80%；并发硬阈值、文案扫描、示例冒烟。

## Success Criteria

- **SC-001**: 三协议示例原生字段通过率 100%。
- **SC-002**: 并发超额 admit 成功次数 = 0。
- **SC-003**: 总览与账本不一致次数 = 0。
- **SC-004**: unresolved 显示为 0 成本次数 = 0。
- **SC-005**: 充值/提现/法币入口数 = 0。

## Assumptions

- 测试额度种子仍走账本 `seed-test-quota`，不是充值产品。
- 网关 Quota 钩子已存在；本 SF 提供买家可见预算与 admit 策略。
