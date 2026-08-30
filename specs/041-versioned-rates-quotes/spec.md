# Feature Specification: 版本化费率、买家倍率与卖家报价

**Feature Branch**: `041-versioned-rates-quotes`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 版本化费率、买家倍率与卖家报价"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF27-版本化费率买家倍率与卖家报价.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 价差？ → A: 买家倍率（bps）必须 ≥ 卖家报价上界，保证任意允许卖家报价下平台价差不为负。
- Q: 无适用费率？ → A: 不猜价，报价结果 `unresolved`。
- Q: 已接受请求？ → A: 锁定的 rate/buyer/seller 版本不可被后续发布改写；只能对后续请求生效。
- Q: 金额？ → A: 整数微单位（scale=6）与万分比 bps；半入最终分录；禁止 IEEE754 入账。
- Q: 权限？ → A: 卖家可见自身报价与平台上下界，不可读取买家倍率；买家可见应付倍率结果，不可见他人报价。
- Q: 基础成本？ → A: 沿用 SF26：有 reported 金额则以其为 base；否则 usage 维度 × 锁定费率。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 锁定版本报价 (Priority: P1)

请求接受时锁定费率、买家倍率、卖家报价版本；结束时用锁定版本算出 buyer debit / seller earning / spread。

**Independent Test**: 同一 capture + lock 重算两次结果相同；发布新版本不改变已锁定请求。

**Acceptance Scenarios**:

1. **Given** 已锁定版本 V1，**When** 发布 V2 后重算该请求，**Then** 仍用 V1 数字。
2. **Given** usage 输入/输出 tokens 与费率行，**When** 报价，**Then** base 为整数乘积之和，buyer/seller/spread 满足公式且 spread≥0。
3. **Given** SF26 reported 金额，**When** 报价，**Then** base 为该金额，usage 费率仅用于差异而不覆盖 base。

---

### User Story 2 - 发布校验 (Priority: P1)

草稿经预演/审批后发布；重叠、单位冲突、卖家越界、负价差无法发布。

**Independent Test**: 上述缺陷各一条负向测试；合法草稿可 publish 且此后不可改。

**Acceptance Scenarios**:

1. **Given** 两行相同键且有效期重叠，**When** publish，**Then** 拒绝 overlap。
2. **Given** 卖家倍率低于 min 或高于 max，**When** 绑定报价，**Then** 拒绝。
3. **Given** published 版本，**When** 修改行或删除，**Then** 拒绝。

---

### User Story 3 - 价格切换并发 (Priority: P1)

切换瞬间的请求分别拿到明确的旧或新完整版本。

**Independent Test**: 并发 lock 与 publish，每个 request_id 只绑定一个完整快照。

**Acceptance Scenarios**:

1. **Given** 线程 A 已 lock V1，**When** 线程 B publish V2，**Then** A 的 lock 仍为 V1。
2. **Given** publish 之后的 lock，**When** 读取，**Then** 为 V2。

---

### User Story 4 - 可见性 (Priority: P1)

卖家看不到买家倍率内部策略；买家看不到他人报价。

**Independent Test**: seller_view 不含 buyer_multiplier_bps；buyer_view 不含他人 seller quotes。

**Acceptance Scenarios**:

1. **Given** 卖家身份，**When** 读价格，**Then** 无买家倍率字段。
2. **Given** 买家身份，**When** 读价格，**Then** 无其它卖家报价列表。

---

### Edge Cases

- 极大 usage 不溢出为负；溢出 → unresolved。
- 无 published 版本时 lock 失败关闭。
- 回滚通过发布新版本，不删除旧 published 行。

## Requirements *(mandatory)*

- **FR-001**: 费率 MUST 支持 provider/model/endpoint/dimension/region/currency 与有效期。
- **FR-002**: 买家倍率 MUST 版本化；卖家倍率 MUST 落在平台上下界。
- **FR-003**: 发布 MUST 拒绝重叠、单位冲突、负价差配置。
- **FR-004**: 请求接受 MUST 锁定完整价格版本。
- **FR-005**: 历史请求 MUST 可用锁定版本重算相同三元组。
- **FR-006**: published MUST 不可原地修改或删除。
- **FR-007**: 无适用费率 MUST unresolved，不得猜价。
- **FR-008**: 金额 MUST 整数定点；最终半入。
- **FR-009**: 卖家 MUST NOT 读取买家倍率。

### Engineering Requirements

- **ER-001**: 扩展 `pricing/v1` 至 1.1.0。
- **ER-002**: Billing 报价引擎 + 发布状态机；Gateway 请求锁。
- **ER-003**: 覆盖率 ≥80%；黄金舍入与并发锁测试。

## Success Criteria

- **SC-001**: 黄金舍入用例通过率 100%。
- **SC-002**: 非法版本发布成功次数 = 0。
- **SC-003**: 已锁请求被新版本改写次数 = 0。
- **SC-004**: 卖家视图泄漏买家倍率次数 = 0。

## Assumptions

- 账本分录由 SF28 落账；本 SF 只产出报价结果与锁。
- V0.2 测试额度，无充值/法币兑现。
