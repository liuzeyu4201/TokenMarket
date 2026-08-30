# Feature Specification: 卖家受限报价与供给工作台

**Feature Branch**: `042-seller-quote-workbench`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 卖家受限报价与供给工作台"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF17-卖家受限报价与供给工作台.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 价差？ → A: 卖家倍率不得超过平台买家倍率，且必须落在 min/max；否则拒绝。
- Q: 历史？ → A: 报价只追加版本，不覆盖；请求锁住当时版本。
- Q: 暂停/容量 0？ → A: 不再接收新的共享请求（admits_new=false）。
- Q: 隐私？ → A: 工作台不含买家身份、请求正文、买家倍率或利润策略。
- Q: 收益？ → A: settled 仅计已结算测试收益；unresolved 单列原因，不计入 settled。账本未接入时不得把未决记成已结算 0 利润。
- Q: 测试额度？ → A: 收益不可提现兑换。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 在边界内报价 (Priority: P1)

卖家看到允许上下界，提交倍率；越界/负价差被拒绝。

**Independent Test**: 边界内成功且产生新 seq；越界与 bps>buyer 拒绝。

**Acceptance Scenarios**:

1. **Given** min=8000 max=11000 buyer=12000，**When** 提交 10000，**Then** 新版本 seq+1 且当前报价为 10000。
2. **Given** 同一边界，**When** 提交 7000 或 13000，**Then** 拒绝且历史不变。

---

### User Story 2 - 供给状态与容量 (Priority: P1)

暂停或容量归零后不再接新共享流量；工作台显示健康与 admits_new。

**Independent Test**: capacity=0 或 paused → admits_new false。

**Acceptance Scenarios**:

1. **Given** listed 连接，**When** 声明容量 0，**Then** admits_new=false。
2. **Given** listed 连接，**When** 暂停，**Then** admits_new=false。

---

### User Story 3 - 工作台总览与隐私 (Priority: P1)

展示健康原因、入选摘要、用量、settled/unresolved；不含买家敏感字段。

**Independent Test**: 公开 JSON 无 buyer_multiplier、buyer_id、raw_body。

**Acceptance Scenarios**:

1. **Given** 卖家打开工作台，**When** 加载，**Then** 见连接、报价、健康、容量、收益分区。
2. **Given** 同一载荷，**When** 扫描字段，**Then** 无买家倍率/身份/正文。

---

### User Story 4 - 审计与限流 (Priority: P1)

报价与供给变更可按 actor 审计；高频更新限流。

**Independent Test**: 审计条数=变更次数；超限返回限流错误。

**Acceptance Scenarios**:

1. **Given** 两次合法报价，**When** 查审计，**Then** 两条且含前后值。
2. **Given** 短时超过限额，**When** 再提交，**Then** 拒绝且不新增版本。

---

### Edge Cases

- 并发报价 seq 单调。
- unresolved 收益不加入 settled。
- 买家工作区打不开工作台。

## Requirements *(mandatory)*

- **FR-001**: 报价 MUST 服务端校验 min/max 与不负价差。
- **FR-002**: 报价历史 MUST 只追加。
- **FR-003**: 暂停或容量 0 MUST 使 admits_new=false。
- **FR-004**: 工作台 MUST NOT 泄露买家身份、正文、买家倍率。
- **FR-005**: unresolved MUST 不计入 settled。
- **FR-006**: 变更 MUST 审计；高频 MUST 限流。

### Engineering Requirements

- **ER-001**: 新增 `seller-workbench/v1`。
- **ER-002**: API 领域+HTTP；前端 `/supply`。
- **ER-003**: 覆盖率 ≥80%；隐私与越界负向测试。

## Success Criteria

- **SC-001**: 越界报价成功率 = 0。
- **SC-002**: 暂停/零容量仍接新共享请求次数 = 0。
- **SC-003**: 工作台泄漏买家倍率次数 = 0。
- **SC-004**: 审计缺失的报价变更次数 = 0。

## Assumptions

- 路由入选摘要在 SF23/24 前可为资格位（admits_new/health），不编造买家请求日志。
- 账本 settled 数字由 SF28 填充；本 SF 提供分区与 unresolved 隔离。
