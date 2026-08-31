# Feature Specification: 运营管理后台

**Feature Branch**: `050-ops-admin-console`

**Created**: 2026-08-31

**Status**: Implemented

**Input**: User description: "V0.2 用户、连接、Project、价格、路由与账本运营后台"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF31-运营管理后台.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 与用户站点关系？ → A: 独立 `/admin` 前缀与管理员 Cookie，不复用买家会话。
- Q: 能否当数据库编辑器？ → A: 不能。无任意 SQL、任意字段 patch、删账本/审计、设最终余额。
- Q: 凭据？ → A: 只显示指纹/能力/健康，无明文凭据入口、导出或网络字段。
- Q: 配置发布？ → A: 草稿→差异→仿真→审批→发布/回滚，禁止直接改 active。
- Q: 高风险？ → A: 向导含影响、step-up、确认；取消/超时无半完成状态。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 运营对象列表与详情 (Priority: P1)

管理员按 RBAC 查看用户/会话、连接、Project、价格、路由、账本未决、告警、审计。

**Independent Test**: 服务端分页；无权限角色 403；连接详情无 secret。

**Acceptance Scenarios**:

1. **Given** 10 万级连接目录，**When** 请求首页，**Then** 仅返回一页且带 next cursor。
2. **Given** 账务只读，**When** 打开发布价格，**Then** 拒绝。
3. **Given** 连接详情/导出，**When** 检查字段，**Then** 仅指纹与健康，无明文。

---

### User Story 2 - 配置发布管线 (Priority: P1)

价格与路由经草稿、差异、仿真后发布；失败不改 active。

**Independent Test**: simulate 失败时 active version 不变；无直接 patch active。

**Acceptance Scenarios**:

1. **Given** 草稿，**When** 查看 diff/simulate，**Then** 显示语义差异与校验结果。
2. **Given** simulate 失败，**When** 尝试发布，**Then** active 不变。
3. **Given** 已发布版本，**When** 直接 PATCH active，**Then** 拒绝。

---

### User Story 3 - 高风险向导与失败态 (Priority: P1)

专享更换、冲正、强退会话使用向导；取消不留半完成；过期健康标为未知。

**Independent Test**: cancel 后无 execute；stale 健康不显示为 live。

**Acceptance Scenarios**:

1. **Given** 向导未确认，**When** 取消或超时，**Then** 无审计成功动作。
2. **Given** 连接探测过期，**When** 打开详情，**Then** 健康为 unknown/stale。
3. **Given** 成功向导，**When** 完成，**Then** 可用 request ID 追踪审计。

---

### Edge Cases

- 查询串可分享且不含密钥。
- 局部失败明确标识，不用过期数据冒充实时。

## Requirements *(mandatory)*

- **FR-001**: 列表 MUST 服务端分页/筛选，不得把全表下发浏览器。
- **FR-002**: 详情 MUST 聚合状态、版本、关联、告警、审计时间线。
- **FR-003**: 价格/路由 MUST 走草稿-差异-仿真-发布-回滚，禁止直接编辑 active。
- **FR-004**: 高风险向导 MUST 展示影响并要求二次认证；取消无半完成。
- **FR-005**: 会话可强制撤销；Connection MUST NOT 暴露明文。
- **FR-006**: MUST NOT 提供 SQL 编辑器、任意 patch、删审计/账本、设最终余额。
- **FR-007**: 过期/失败健康 MUST 标 unknown/stale。

### Engineering Requirements

- **ER-001**: `admin-console/v1` 契约；扩展 RBAC 只读动作。
- **ER-002**: admin-service ops catalog + config pipeline + wizard。
- **ER-003**: 前端 `/admin` 独立壳；覆盖率 ≥80%；RBAC 负向与泄漏扫描。

## Success Criteria

- **SC-001**: 列表响应条数 ≤ 页大小。
- **SC-002**: 无权限写成功次数 = 0。
- **SC-003**: 明文 secret 在页面/导出出现次数 = 0。
- **SC-004**: 向导取消后成功审计次数 = 0。
- **SC-005**: 直接改 active 成功次数 = 0。

## Assumptions

- 真实 10 万行库表可用虚拟目录证明分页，不把全表载入内存。
- SLO 仪表盘深化属 SF32。
