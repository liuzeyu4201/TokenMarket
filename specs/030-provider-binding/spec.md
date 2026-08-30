# Feature Specification: 多协议 Provider Binding

**Feature Branch**: `030-provider-binding`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 多协议 Provider Binding"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF11-多协议ProviderBinding.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: Binding 如何对应 Project 模式？ → A: Binding 的供给方式必须与 Project 不可变 mode 相同。shared Binding 声明可接受厂商/模型/区域；dedicated Binding 指向唯一专享 Connection。不一致则保存与发布均拒绝。
- Q: Connection 与价格尚未落地？ → A: 发布前经端口校验。无 Connection 事实则专享发布失败关闭。价格可用性以冻结日目录中该协议稳定数据面是否存在为准；未知模型拒绝。不得伪造价格或连接健康。
- Q: 生效版本如何切换？ → A: 每个 Project+protocol 仅一个 active。发布写入新版本并使旧 active 失效。已发出请求锁定当时 version；新请求直读生效版本，传播 ≤1s，无缓存。
- Q: 专享 Connection 失效？ → A: Binding 进入 degraded，明确失败关闭，不得回退共享池或其他连接。
- Q: 跨协议？ → A: 禁止。OpenAI 请求不得因模型名相近进入 Anthropic 或 Vertex Binding。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 为三协议各自发布 Binding (Priority: P1)

买家为同一 Project 分别配置并发布 OpenAI、Anthropic、Vertex Binding，拿到对应原生 SDK 入口提示（不含上游凭据）。

**Why this priority**: 多协议是后续代理与路由的资格根。

**Independent Test**: 同一 Project 发布三协议；各协议 SDK 提示协议不同且无 secret。

**Acceptance Scenarios**:

1. **Given** 买家工作区中的 Project，**When** 为 openai/anthropic/vertex 各发布一个与 Project mode 一致的 Binding，**Then** 三份均为 active，且各有原生 base URL/鉴权方式/协议版本提示。
2. **Given** 已发布 Binding，**When** 读取 SDK 提示，**Then** 正文不含上游凭据或连接 secret。
3. **Given** 卖家工作区，**When** 创建 Binding，**Then** 403。

---

### User Story 2 - 草稿、校验、发布与单生效版本 (Priority: P1)

配置走草稿→校验→发布。同一 Project+protocol 并发发布只留下一个 active version。

**Why this priority**: 防止双活配置导致路由歧义。

**Independent Test**: 两草稿并发发布，恰好一个 active；失败方不改变已生效版本。

**Acceptance Scenarios**:

1. **Given** 草稿，**When** 校验通过后发布，**Then** 成为该协议唯一 active，version 递增。
2. **Given** 两请求同时发布同一协议，**When** 完成，**Then** 仅一行 status=active。
3. **Given** 已锁定 version 的在途语义，**When** 随后发布新版本，**Then** 旧 version 行不变，新请求读到新 version。

---

### User Story 3 - 模式、协议与降级约束 (Priority: P1)

mode 不一致、跨协议映射、模型/厂商篡改均被拒绝。专享 Connection 失效后 Binding degraded 且不回退共享池。

**Why this priority**: 总纲硬约束。

**Independent Test**: shared Project 拒绝 dedicated Binding；openai Binding 拒绝 anthropic provider；degraded 后准入失败且无 shared 候选。

**Acceptance Scenarios**:

1. **Given** shared Project，**When** 保存/发布 dedicated Binding，**Then** 拒绝，库中无 active dedicated。
2. **Given** openai Binding，**When** 以 anthropic/vertex 或未允许模型做准入，**Then** 拒绝。
3. **Given** dedicated Binding 的 Connection 被标记失效，**When** 新请求准入，**Then** degraded 失败关闭，不出现共享池候选。

---

### User Story 4 - 启用协议与买家 UI (Priority: P2)

发布成功后，SF10 的「启用协议」可通过 Binding 检查。买家在 Project 详情配置 Binding 并看到 SDK 提示。

**Why this priority**: 打通 SF10 失败关闭缺口。

**Independent Test**: 无 Binding 启用仍 409；发布后启用成功。UI 展示三协议与模式后果，无凭据字段回显。

**Acceptance Scenarios**:

1. **Given** 已发布 openai Binding，**When** 启用 openai 协议，**Then** 成功。
2. **Given** 未发布 Binding，**When** 启用协议，**Then** 仍 `PROVIDER_BINDING_REQUIRED`。
3. **Given** 买家打开 Project 详情，**When** 查看 Binding 区，**Then** 可创建/发布并看到无秘密的 SDK 提示。

---

### Edge Cases

- 归档 Project 拒绝新 Binding。
- 跨账号 Binding ID 与不存在同形 404。
- 控制面目录端点不得作为 Binding 能力依据。
- 停用 Binding 不影响历史锁定 version 行。
- 本 SF 不实现真实 Connection 实体、代理 Key、账本或跨协议转换。

## Requirements *(mandatory)*

- **FR-001**: 每个 Project+protocol MUST 至多一个 active Binding。
- **FR-002**: 配置 MUST 支持草稿、校验、发布版本；发布 MUST 递增 version。
- **FR-003**: Binding 供给方式 MUST 等于 Project mode，否则保存/发布拒绝。
- **FR-004**: shared Binding MUST 声明可接受厂商/模型（及可选区域）；dedicated Binding MUST 指向唯一 Connection 标识。
- **FR-005**: 发布 MUST 校验协议能力（目录稳定数据面）与价格可用性端口；专享 MUST 校验 Connection 端口。
- **FR-006**: 请求准入 MUST 锁定 Binding version；修改/停用 MUST NOT 改写已发布行。
- **FR-007**: MUST NOT 做跨协议映射；协议与厂商 MUST 一致。
- **FR-008**: 专享 Connection 失效 MUST 使 Binding 为 degraded，MUST NOT 回退共享池。
- **FR-009**: SDK 提示 MUST 含原生 base URL、鉴权方式、协议版本；MUST NOT 含上游凭据。
- **FR-010**: 仅买家工作区所有者可写；IDOR 同形 404。
- **FR-011**: 存在 active/degraded Binding 时，SF10 启用协议检查 MUST 通过；否则仍失败关闭。

### Engineering Requirements

- **ER-001 — Contracts**: 新增 `provider-binding/v1` OpenAPI。
- **ER-002 — Security**: 会话身份、工作区透镜、CSRF、无凭据回显。
- **ER-003 — Data**: 部分唯一保证单 active；已发布行不可变。
- **ER-004 — Performance**: 新请求读取生效版本 ≤1s。
- **ER-005 — Reliability**: 并发发布仅一胜。
- **ER-006 — Observability**: 发布/降级审计含 project、protocol、version、request_id，无秘密。
- **ER-007 — Accessibility**: Binding 表单有标签；SDK 提示与错误关联。

### Key Entities

- **ProviderBinding**: Project、protocol、supply_mode、status、version、配置快照。
- **BindingVersionLock**: 请求使用的 version 标识（发布后不变的行）。
- **SdkHint**: base URL、auth_scheme、protocol_version。
- **ConnectionFact / PriceAvailability**: 端口，非本 SF 实体表。

## Success Criteria

- **SC-001**: 同一 Project 三协议同时 active 的测试通过率 100%。
- **SC-002**: 同一 Project+protocol 并发发布后 active 行数 = 1。
- **SC-003**: mode 不一致保存/发布成功次数 = 0。
- **SC-004**: 跨协议或未允许模型准入成功次数 = 0。
- **SC-005**: dedicated degraded 后新请求准入成功次数 = 0，且响应不含共享池候选。
- **SC-006**: SDK 提示中凭据/secret 字段出现次数 = 0。
- **SC-007**: 发布后 1 秒内新请求读到新 version 的失败次数 = 0。

## Assumptions

- Connection 实体与健康探针在 SF14/SF15 落地；本 SF 提供端口与 degraded 语义。
- 版本化费率在 SF27 落地；本 SF 以目录稳定数据面作为价格/能力可用性代理。
- 代理 Key 原生鉴权材料由 SF12 签发；本 SF 只提示 scheme。
- 买家 UI 复用设计系统。
