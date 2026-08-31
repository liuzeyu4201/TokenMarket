# Feature Specification: 全链路可观测、SLO 与告警处置

**Feature Branch**: `051-observability-slo-alerts`

**Created**: 2026-08-31

**Status**: Implemented

**Input**: User description: "V0.2 全链路可观测、SLO 与告警处置"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF32-全链路可观测SLO与告警处置.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: SLO 窗口与发布停止？ → A: 30 天滚动；剩余错误预算 <20% 时冻结发布。
- Q: 指标标签？ → A: 仅允许有界标签；禁止 user/project/request ID。
- Q: 异步关联？ → A: usage/ledger 以 kind=link 使用同一 request ID。
- Q: 敏感信息？ → A: 日志/trace/exemplar 统一脱敏，测试 secret 零命中。
- Q: 告警范围？ → A: upstream 慢、无候选、事件积压、未决突增、连接故障，含 runbook/owner/升级。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 用 request ID 串联全链路 (Priority: P1)

值班人员给出任意 request ID，看到代理、路由、upstream、用量与账本 hops（异步为 link）。

**Independent Test**: 注入五段 hops 后按 ID 取出完整链；缺段标 unknown。

**Acceptance Scenarios**:

1. **Given** 同一 request ID 的五段记录，**When** 查询，**Then** 返回 proxy/route/upstream/usage/ledger。
2. **Given** 异步结算 hop，**When** 查看，**Then** kind 为 link 且 request ID 相同。
3. **Given** 日志/trace/exemplar 含测试密钥，**When** 扫描，**Then** 命中数为 0。

---

### User Story 2 - SLO 与错误预算 (Priority: P1)

数据面 99.9%、管理面 99.5%；仪表盘显示可用性、延迟与剩余错误预算；预算将尽则停止发布。

**Independent Test**: 用固定 good/total 计算可用性与冻结标志。

**Acceptance Scenarios**:

1. **Given** 数据面 9990/10000 成功，**When** 计算，**Then** 可用性 99.9% 且不冻结。
2. **Given** 管理面错误使剩余预算 <20%，**When** 计算，**Then** freeze=true。
3. **Given** 平台与 upstream 时延，**When** 观察，**Then** 二者可分别读取。

---

### User Story 3 - 可执行告警与基数保护 (Priority: P1)

五类故障触发带阈值、dashboard、runbook、owner、升级路径的告警；高基数标签被拒绝。

**Independent Test**: 样本越过阈值则 firing；user_id 标签被拒绝。

**Acceptance Scenarios**:

1. **Given** upstream p95 超阈，**When** 评估，**Then** `upstream_slow` firing。
2. **Given** 无候选/积压/未决突增/连接故障，**When** 评估，**Then** 对应告警 firing。
3. **Given** 指标尝试 user_id 或超系列上限，**When** 注册，**Then** 拒绝。

---

### Edge Cases

- 局部 hop 缺失标 unknown，不把过期数据当实时。
- SSE/WebSocket 记录建连、首事件、持续、关闭原因。
- 不记录 prompt/response、文件内容、密钥、token、验证码、手机号明文。

## Requirements *(mandatory)*

- **FR-001**: request/trace ID MUST 跨 Gateway、服务、事件、worker；异步 MUST 用 link。
- **FR-002**: RED MUST 按 protocol/endpoint/status；禁止无界 label。
- **FR-003**: MUST 区分平台新增延迟与 upstream 延迟；SSE/WS MUST 记录建连/首事件/持续/关闭原因。
- **FR-004**: 数据面 SLO 99.9%，管理面 99.5%；MUST 定义 SLI、30 天窗口、错误预算、剩余 <20% 冻结发布。
- **FR-005**: 告警 MUST 含影响、阈值、dashboard、runbook、owner、升级路径。
- **FR-006**: 日志/trace/exemplar MUST 脱敏；测试 secret 命中 = 0。
- **FR-007**: 专用指标覆盖路由无候选、事件积压、未决账务、连接健康。

### Engineering Requirements

- **ER-001**: `observability/v1` 契约（SLO、标签、告警、trace）。
- **ER-002**: Gateway SLO 指标 + 可选透传埋点；admin-service SLO/告警评估。
- **ER-003**: Grafana 仪表盘、Prometheus 规则、runbook；覆盖率 ≥80%。

## Success Criteria

- **SC-001**: 抽样 request ID 能串联五段状态。
- **SC-002**: 仪表盘可分别计算数据面/管理面可用性、延迟、错误预算。
- **SC-003**: 五类故障告警触发次数与注入次数一致。
- **SC-004**: 脱敏扫描测试 secret 命中 = 0。
- **SC-005**: 高基数标签被拒绝次数 = 尝试次数。

## Assumptions

- Grafana OSS 由 SF02 提供；本功能提供可导入仪表盘与规则，不新建监控栈。
- 容量压测中的真实 Prometheus 负载属 SF33；本功能以系列上限保护证明基数受控。
