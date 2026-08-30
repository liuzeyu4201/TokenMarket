# Feature Specification: 厂商原生花费与多维用量采集

**Feature Branch**: `040-native-spend-usage-capture`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 厂商原生花费与多维用量采集"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF26-厂商原生花费与多维用量采集.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 解析失败或缺失？ → A: `cost_status=unresolved`，不得把未知记为 0。
- Q: 金额与 usage 共存？ → A: 两者都保存；结算输入选金额（reported），usage 用于差异检测；不以 computed 覆盖 reported。
- Q: 无费率时仅有 usage？ → A: 采集维度并标 `rated`（待 SF27 费率计算）；无金额且无适用 usage 则为 unresolved。
- Q: 目录 `metering_source=none`？ → A: 明确策略为不计量，不产生 0 成本，不进入结算。
- Q: 证据？ → A: 保存标准化字段与 digest；事件/日志不含完整请求响应正文或文件明文。
- Q: 真实厂商？ → A: 夹具解析；付费冒烟不在本 Goal。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 优先采集可验证花费 (Priority: P1)

上游返回明确货币花费时，以其为结算基础并保留 usage。

**Independent Test**: 夹具同时含 cost 与 tokens 时 settlement_basis=reported，tokens 仍在。

**Acceptance Scenarios**:

1. **Given** OpenAI 响应含 usage.tokens 与 cost，**When** 解析，**Then** reported 金额为结算输入且 tokens 非空。
2. **Given** 同一原始正文重放，**When** 同一 parser version，**Then** 标准化结果与 digest 相同。

---

### User Story 2 - 无金额时采集多维 usage (Priority: P1)

无货币字段时采集 input/output/cache/reasoning 等适用维度，供后续费率计算。

**Independent Test**: Anthropic/Vertex/OpenAI 夹具解析值与原生字段一致；缺字段为 null 不是 0。

**Acceptance Scenarios**:

1. **Given** Anthropic message usage 仅 tokens，**When** 解析，**Then** cost_status=rated 且 reported_cost 为 null。
2. **Given** 响应无 usage 且目录策略为 usage/mixed，**When** 解析，**Then** unresolved，tokens 保持 null。

---

### User Story 3 - 流式与提前断开 (Priority: P1)

SSE 结束事件中的 usage 被采集；客户端提前断开仍解析已见证据。

**Independent Test**: 流式夹具最后一帧 usage 生效；截断流在已出现 usage 时得到 partial 完整字段。

**Acceptance Scenarios**:

1. **Given** Anthropic SSE message_start+message_delta usage，**When** 解析流，**Then** input 与 output 均齐。
2. **Given** 流在 usage 帧之后断开，**When** 解析已缓冲字节，**Then** 不把缺失维填 0。

---

### User Story 4 - 异常进入未决 (Priority: P1)

负数、溢出、未知单位、解析失败进入 unresolved。

**Independent Test**: 各异常夹具 cost_status=unresolved 且无伪造 0 金额。

**Acceptance Scenarios**:

1. **Given** 负 token 或不可解析 cost，**When** 解析，**Then** unresolved。
2. **Given** 目录 metering_source=none，**When** 结束，**Then** 不产生结算金额 0。

---

### Edge Cases

- 控制面端点不采集。
- 异步资源结果与普通 JSON 使用同一 parser version。
- 日志禁止 raw_body/api_key。

## Requirements *(mandatory)*

- **FR-001**: 每个 stable 端点 MUST 有 catalog 计量策略（reported / rated / unresolved / none）。
- **FR-002**: 可验证货币花费 MUST 优先作为结算输入。
- **FR-003**: 无金额时 MUST 采集适用 usage 维度；缺失为 null 不得填 0。
- **FR-004**: 金额与 usage 共存 MUST 保留两者且不以 computed 覆盖 reported。
- **FR-005**: 解析失败、未知单位、溢出、负数 MUST unresolved。
- **FR-006**: 同一证据 + parser version MUST 重放一致。
- **FR-007**: 事件与日志 MUST NOT 含完整正文或密钥。
- **FR-008**: 流式结束事件或已见片段 MUST 尽量补全 usage。

### Engineering Requirements

- **ER-001**: 扩展 `usage/v1` 至 1.1.0。
- **ER-002**: 网关 `usageparse` 解析器 + 内核挂钩；Billing 校验观察信封。
- **ER-003**: 变更包覆盖率 ≥80%。

## Success Criteria

- **SC-001**: 伪造未知成本为 0 的次数 = 0。
- **SC-002**: 三厂商适用夹具解析与原生字段一致率 100%。
- **SC-003**: 双字段共存时 reported 被覆盖次数 = 0。
- **SC-004**: 相同证据重放 digest 不一致次数 = 0。

## Assumptions

- 版本化费率（computed 金额）由 SF27 提供；本 SF 在仅有 usage 时标记 `rated` 并保留维度。
- 账本结算由 SF28/SF29 消费观察，本 SF 不写分录。
