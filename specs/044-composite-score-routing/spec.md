# Feature Specification: 健康、延迟、容量、价格综合评分路由

**Feature Branch**: `044-composite-score-routing`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 健康、延迟、容量、价格综合评分路由"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF24-健康延迟容量价格综合评分路由.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 评分范围？ → A: 仅 SF23 合格集；硬门槛失败者不得因高分入选。
- Q: 缺指标？ → A: 按保守最差值计分，不得默认最佳。
- Q: 重放？ → A: 相同输入、policy version、种子 → 相同排名与选择。
- Q: 探索？ → A: 可选加权随机，但只在合格集内；种子确定。
- Q: 策略变更？ → A: 只影响新请求；已锁定 policy version 不改。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 四因素加权选择 (Priority: P1)

对合格候选按健康、延迟、容量、价格打分并选择。

**Independent Test**: 单独改善任一因素，其分项与总分按文档方向上升；其它不变。

**Acceptance Scenarios**:

1. **Given** 两名合格候选仅健康不同，**When** 评分，**Then** 更健康者 health 与 total 更高。
2. **Given** 仅延迟更低，**When** 评分，**Then** latency 分与 total 更高。
3. **Given** 仅剩余容量更大，**When** 评分，**Then** capacity 分与 total 更高。
4. **Given** 仅卖家报价更低（对买家更优），**When** 评分，**Then** price 分与 total 更高。

---

### User Story 2 - 可重放与策略版本 (Priority: P1)

固定输入与种子 100% 重放；新策略只影响新请求。

**Independent Test**: Rank 两次 JSON 相同；切换 policy 后旧 snapshot 选择不变。

**Acceptance Scenarios**:

1. **Given** 相同 signals/policy/seed，**When** 两次 Rank，**Then** 排名与胜出 ID 相同。
2. **Given** 请求已记录 policy v1，**When** 发布 v2，**Then** 重放仍用 v1。

---

### User Story 3 - 保守缺测与容量 (Priority: P1)

缺测按最差；选择不超过剩余容量。

**Independent Test**: 缺 latency 的连接 latency 分为 0；仿真选择次数 ≤ remaining。

**Acceptance Scenarios**:

1. **Given** 无延迟样本，**When** 评分，**Then** latency=0 且不得因此胜过有数据的健康连接（在其它相等时）。
2. **Given** remaining=1，**When** 连续选择，**Then** 不超过 1 次胜出（原子预占）。

---

### Edge Cases

- 合格集为空：不评分，NO_UPSTREAM。
- 并列：按 connection_id 字典序（无探索时）。
- 探索权重 >0 时仍不得选出被硬过滤者。

## Requirements *(mandatory)*

- **FR-001**: 评分 MUST 仅作用于 SF23 合格集。
- **FR-002**: 四因子 MUST 均可独立影响总分。
- **FR-003**: 缺测 MUST 用保守值。
- **FR-004**: 相同输入+种子 MUST 可重放。
- **FR-005**: 策略变更 MUST 只影响新请求。
- **FR-006**: 选择 MUST 尊重剩余容量预占。
- **FR-007**: 决策 MUST 记录分项、胜出原因、policy version、种子。

### Engineering Requirements

- **ER-001**: `route-decision/v1` 1.2.0 增加 scoring 政策。
- **ER-002**: `internal/domain/score` + ScoringSelector。
- **ER-003**: 覆盖率 ≥80%；单调性与重放测试。

## Success Criteria

- **SC-001**: 硬过滤失败者入选次数 = 0。
- **SC-002**: 固定输入重放不一致次数 = 0。
- **SC-003**: 四因子单调性用例通过率 100%。
- **SC-004**: 超容量选择次数 = 0。

## Assumptions

- 管理员灰度 UI 在 SF31；本 SF 提供 policy registry 与重放接口。
- 全量 500 RPS 剖析属 SF33；本 SF 保证无全表扫描、O(n) 合格集。
