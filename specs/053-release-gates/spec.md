# Feature Specification: 全流程测试、安全、兼容、可访问性与发布门禁

**Feature Branch**: `053-release-gates`

**Created**: 2026-08-31

**Status**: Implemented

**Input**: User description: "V0.2 全流程 E2E、安全、兼容、可访问性与发布门禁"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF34-全流程测试安全兼容可访问性与发布门禁.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 独立渗透/真实短信/付费厂商冒烟/生产部署？ → A: 未授权则列为发布阻塞项，不得宣称公开上线。
- Q: 硬门禁可否豁免？ → A: 不得豁免 P0/P1、Critical/High、稳定端点或关键 E2E。
- Q: P2/Medium？ → A: 仅书面接受，含 owner、期限、影响。
- Q: 公开上线 go/no-go？ → A: 任一硬门禁或未关闭渗透 Critical/High 则为 no-go。
- Q: 实现完成 vs 公开上线？ → A: 实现完成可在阻塞项清单齐全时成立；公开上线必须全部外部证据齐备。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 需求到证据追踪 (Priority: P1)

发布负责人能看到 SF01–SF34 每条验收都有 requirement→test→result→artifact。

**Independent Test**: 扫描 specs 与测试映射，缺项则 fail。

**Acceptance Scenarios**:

1. **Given** 34 个 SF，**When** 生成矩阵，**Then** 每条有目录、分支、converge 证据。
2. **Given** 缺失 evidence，**When** 评估，**Then** mapping 不为 100%。

---

### User Story 2 - 关键旅程与 a11y (Priority: P1)

买家、卖家、管理员关键路径可测；登录/后台页面通过自动 a11y 门禁。

**Independent Test**: 组合领域服务跑买家/账本/管理员路径；Vitest 扫描关键页。

**Acceptance Scenarios**:

1. **Given** 买家创建 Project，**When** 试图改 mode，**Then** MODE_IMMUTABLE。
2. **Given** 账本分录，**When** 修改或删除，**Then** 拒绝。
3. **Given** 首页/登录/运营登录，**When** a11y 扫描，**Then** 无严重违规。

---

### User Story 3 - 发布 go/no-go (Priority: P1)

门禁引擎根据硬门槛和阻塞项给出 go 或 no-go；公开上线缺渗透则为 no-go。

**Independent Test**: 构造证据夹具，断言 fail-closed。

**Acceptance Scenarios**:

1. **Given** P0 缺陷 >0，**When** 评估公开上线，**Then** no-go。
2. **Given** 渗透未完成，**When** 评估公开上线，**Then** no-go 且列入阻塞项。
3. **Given** 映射完整且无 P0、不宣称公开上线，**When** 评估实现完成，**Then** go-with-blockers。

---

### Edge Cases

- 不得用豁免绕过硬门禁。
- 连续 3 次 CI 必须同一候选 commit；一次 flaky 即失败。
- 回滚不得删除账本数据。

## Requirements *(mandatory)*

- **FR-001**: MUST 建立覆盖 SF01–SF34 的 requirement→test→result→artifact 矩阵。
- **FR-002**: E2E MUST 覆盖买家 Project 不可变 mode、账本不可变、管理员隔离会话。
- **FR-003**: MUST 执行安全不变量：无跨协议转换、无明文凭据、无充值提现、未决不得记 0。
- **FR-004**: 关键 UI MUST 有 WCAG 2.2 AA 自动扫描（标签、名称、焦点语义）。
- **FR-005**: 发布评估 MUST fail-closed：P0/P1 或安全 Critical/High 则 no-go。
- **FR-006**: 未授权外部证据 MUST 列为发布阻塞项，不得冒充完成。
- **FR-007**: P2/Medium 接受记录 MUST 含 owner 与期限，否则视为未接受。
- **FR-008**: 公开上线签署 MUST 在硬门禁全过且渗透 Critical/High 关闭后。

### Engineering Requirements

- **ER-001**: `release-gate/v1` 契约。
- **ER-002**: 可执行 go/no-go 评估器与追踪扫描。
- **ER-003**: 负向不变量与 a11y 测试；覆盖率 ≥80%。

## Success Criteria

- **SC-001**: SF01–SF34 映射覆盖率 = 100%。
- **SC-002**: 公开上线在缺渗透时 go 次数 = 0。
- **SC-003**: 账本 mutate/delete 成功次数 = 0。
- **SC-004**: Project mode patch 成功次数 = 0。
- **SC-005**: 关键页严重 a11y 违规 = 0。

## Assumptions

- 独立渗透、真实短信、付费厂商冒烟、生产部署、git push 未授权。
- 墙钟 30m/2h 容量由 `CAPACITY_FULL=1` 启用；未跑则列入公开上线阻塞项。
