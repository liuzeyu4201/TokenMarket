# Feature Specification: 连接验证、能力发现与健康状态

**Feature Branch**: `033-connection-verify-health`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 连接验证、能力发现与健康状态"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF15-连接验证能力发现与健康状态.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 谁能验证？ → A: 仅卖家工作区中的连接所有者可手动复验。买家 403。路由经内部身份读取健康快照，不解密凭据。
- Q: 明文？ → A: 验证路径可内部 unwrap（purpose=verify），但卖家诊断、公开 API、日志、审计不得含 secret 或完整 upstream 响应。
- Q: 能力快照？ → A: 发现结果与 Endpoint Catalog 求交；仅 stable 且非 control_plane 的已验证能力入快照。未知能力默认不可路由。旧快照版本化保留。
- Q: 健康抖动？ → A: 计划探测用连续成功/失败阈值（成功≥2 才 healthy，失败≥3 才 unhealthy）；限流记 degraded。凭据类错误（无效/无权限/区域错误）立即 unhealthy。手动复验立即应用结果，目标时间内可恢复。
- Q: 探测预算？ → A: 全局并发上限与抖动/退避；单次 tick 不得超过预算。不得创建文件、批任务或调优任务。本环境用可注入探测夹具，不发起付费厂商调用。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 三厂商可区分验证 (Priority: P1)

卖家验证连接后，合法、非法凭据、权限不足、区域错误、限流、厂商故障得到可区分状态，且看不到明文。

**Why this priority**: 错误分类决定卖家能否修复，也决定路由是否可用。

**Independent Test**: 对同一连接注入六类探测结果，公开响应仅含类别与脱敏原因。

**Acceptance Scenarios**:

1. **Given** 合法凭据探测成功，**When** 手动验证，**Then** 健康为 healthy（或达到成功阈值后），诊断无 secret。
2. **Given** 无效凭据 / 无权限 / 区域错误，**When** 验证，**Then** 分别为 invalid_credential / forbidden / region_mismatch，且 unhealthy。
3. **Given** 限流，**When** 验证，**Then** degraded，不因单次限流直接 unhealthy。
4. **Given** 买家工作区，**When** POST verify，**Then** 403。

---

### User Story 2 - 能力快照与目录交集 (Priority: P1)

能力发现结果只保留目录内已验证项；旧快照可查询。

**Why this priority**: 未知或控制面能力不得进入路由。

**Independent Test**: 探测返回目录外路径/模型时快照不含该项；连续两次发现产生两个版本。

**Acceptance Scenarios**:

1. **Given** 探测列出目录内与目录外端点，**When** 生成快照，**Then** 仅 stable 非 control_plane 目录项保留。
2. **Given** 已有快照，**When** 再次成功发现，**Then** 新版本号递增，旧版本仍可读取。
3. **Given** 快照为空，**When** 路由读取，**Then** 该连接能力不可路由。

---

### User Story 3 - 健康滞后与探测预算 (Priority: P1)

计划探测不因单次 upstream 故障上下架；调度遵守并发预算。

**Why this priority**: 防止抖动与同步风暴。

**Independent Test**: 从 healthy 一次 upstream_fault 不变 unhealthy；1000 条到期连接一次 tick 不超过并发预算。

**Acceptance Scenarios**:

1. **Given** 已 healthy，**When** 一次 upstream_fault 计划探测，**Then** 状态为 degraded 而非 unhealthy。
2. **Given** 连续失败达到阈值，**When** 再探测，**Then** unhealthy。
3. **Given** 1000 条均到期，**When** 一次调度，**Then** 实际并发/处理数 ≤ 全局预算，其余仍待下次。

---

### User Story 4 - 手动复验与卖家诊断 UI (Priority: P2)

凭据修复后卖家可立即复验；页面展示健康原因与快照，无明文。

**Why this priority**: 卖家需要可操作的恢复路径。

**Independent Test**: 从 unhealthy 手动成功复验后状态恢复；UI 无 secret。

**Acceptance Scenarios**:

1. **Given** 先前凭据错误 unhealthy，**When** 替换凭据并手动复验成功，**Then** 状态在本次请求内恢复为 healthy。
2. **Given** 卖家连接页，**When** 查看，**Then** 可见健康与能力摘要，无 secret。

---

### Edge Cases

- 删除后的连接不可验证（404）。
- 探测超时/夹具不可用 → unknown 或 upstream_fault，不得抛明文。
- 探测不得跟随 SSRF 重定向、不得写文件或创建批任务。
- Preview/beta 目录项不进入默认快照。
- 本 SF 不实现报价、供给上架状态机全量（SF16）与路由评分（SF24）。

## Requirements *(mandatory)*

- **FR-001**: 创建/更新后以及手动复验 MUST 执行鉴权与最小安全调用（经内部 verify unwrap）。
- **FR-002**: 验证结果 MUST 区分 invalid_credential、forbidden、region_mismatch、rate_limited、upstream_fault 与成功。
- **FR-003**: 能力快照 MUST 为发现结果与 Endpoint Catalog 的交集；未知能力不可路由。
- **FR-004**: 快照 MUST 版本化保留。
- **FR-005**: 健康状态 MUST 为 healthy | degraded | unhealthy | unknown，带原因与时间。
- **FR-006**: 计划探测 MUST 使用连续阈值防抖动；手动复验可立即生效。
- **FR-007**: 探测 MUST 有全局并发预算、抖动与退避；禁止同步风暴。
- **FR-008**: 卖家诊断、日志、审计 MUST NOT 含 secret 或完整 upstream 响应。
- **FR-009**: 买家工作区 MUST 不能触发验证。
- **FR-010**: 路由 MUST 能读取统一健康快照（内部身份），不得借此读明文。

### Engineering Requirements

- **ER-001**: 扩展 `provider-connection/v1`（expand-only，1.2.0）。
- **ER-002**: CSRF 保护写路径；内部健康读取用内部令牌。
- **ER-003**: Postgres SoR；探测夹具可注入；默认 fail-closed 不发起付费调用。
- **ER-004**: 领域覆盖率 ≥80%；六类结果与预算负向测试。

## Success Criteria

- **SC-001**: 六类凭据/探测结果区分正确率 100%。
- **SC-002**: 快照中出现目录外或 control_plane 能力的次数 = 0。
- **SC-003**: 单次 upstream 故障导致 healthy→unhealthy 的次数 = 0。
- **SC-004**: 1000 连接一次调度超过并发预算的次数 = 0。
- **SC-005**: 公开诊断/日志中明文出现次数 = 0。

## Assumptions

- 本地/测试用 VendorProbe 夹具代替真实厂商；生产探测适配器属于后续运维接入，仍须走同一端口与预算。
- SF16 消费健康与快照做供给生命周期；SF23/SF24 消费内部健康快照做资格与评分。
