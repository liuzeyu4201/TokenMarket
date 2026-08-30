# Feature Specification: V0.2 契约与端点目录治理

**Feature Branch**: `020-endpoint-catalog-governance`

**Created**: 2026-08-31

**Status**: Implemented

**Input**: User description: "V0.2 契约与端点目录治理：建立三厂商 Endpoint Catalog 与跨服务 HTTP/事件契约唯一事实源"

**Language**: 本规格默认简体中文（constitution Principle VIII）。代码标识、API 字段、CLI 命令、路径、环境变量、协议、标准、库名称和专有名词保持原样。

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF01-V0.2契约与端点目录治理.md`

**Freeze date**: 2026-08-31（V0.2_0831 发布冻结日）

## Clarifications

### Session 2026-08-31

本会话未向用户重复提问。以下决策均已在 V0.2 总纲、API 协议兼容基线与 SF01 来源文档中确认，直接编码进本规格：

- Q: 冻结日如何确定？ → A: 2026-08-31，与 V0.2_0831 版本文档日期一致。
- Q: 目录覆盖哪些厂商？ → A: 仅 OpenAI、Anthropic、Google Vertex 公开稳定模型数据面；V0.1 Volcano 契约继续独立存在，不并入本目录作为第四厂商。
- Q: Preview/Beta 如何处理？ → A: 可逐项登记，默认拒绝；仅当记录显式为 preview/beta 且调用方 Project 已 opt-in 时允许。
- Q: 控制面如何与未登记区分？ → A: 控制面必须登记为 `control_plane`，返回 `CONTROL_PLANE_NOT_ALLOWED`；未登记路径返回 `ENDPOINT_NOT_CATALOGED`。
- Q: 厂商文档含糊时如何分类？ → A: 不得进入 `stable`；保留评审证据后再决策。
- Q: 跨服务领域契约是否本 SF 实现业务行为？ → A: 否。本 SF 只发布 Project、Provider Connection、route decision、usage、pricing、ledger、audit 的版本化 HTTP/事件契约与兼容策略；领域实现属于后续 SF。
- Q: 目录主版本不兼容时的行为？ → A: 消费者进程启动失败关闭，不得带不兼容目录提供数据面。
- Q: 人类可读清单来源？ → A: 必须由同一机器可读目录确定性生成；工作树不得出现非确定性差异。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 冻结日稳定端点可枚举、可测试 (Priority: P1)

发布负责人需要一份机器可读的 Endpoint Catalog，使“三厂商全部公开稳定模型数据面全兼容”成为可枚举、可冻结、可测试的发布范围，而不是口头承诺。Gateway、能力发现、路由、计量、文档和兼容测试共同消费同一目录版本。

**Why this priority**: 没有唯一目录，后续透传、路由、计量和发布门禁无法证明覆盖率 100%。

**Independent Test**: 仅凭目录文件与 schema 即可证明：三厂商冻结日稳定数据面端点被唯一记录、无重复 method/path/version、每条 stable 记录可追溯官方来源、合同测试夹具版本和负责 SF。

**Acceptance Scenarios**:

1. **Given** 冻结日为 2026-08-31 的已评审目录，**When** 校验器枚举 `provider + protocol_version + method + path_template`，**Then** 每个组合最多出现一次，且 OpenAI、Anthropic、Google Vertex 的冻结日稳定数据面家族均有记录。
2. **Given** 一条 stable 记录，**When** 查看其追溯字段，**Then** 必须包含官方文档来源、合同测试夹具版本和负责 SF（SF19/SF20/SF21 或本 SF 的目录治理标识）。
3. **Given** 人为加入重复 method/path/version，**When** 运行目录校验，**Then** 校验失败并指出冲突键。

---

### User Story 2 - 不完整目录记录被 schema 拒绝 (Priority: P1)

契约维护者提交目录变更时，缺少稳定性、状态性、传输、计量来源或测试夹具的记录必须被自动拒绝，不能进入工作树或启动消费者。

**Why this priority**: 目录质量是后续 SF 的硬前置；缺字段会导致未知行为被默许转发。

**Independent Test**: 对缺字段、非法枚举、缺追溯信息的夹具运行校验器，全部失败；完整合法记录通过。

**Acceptance Scenarios**:

1. **Given** 一条缺少 `stability`、`stateful`、`transport`、`metering_source` 或 `test_fixture_version` 的记录，**When** 执行 schema/完整性校验，**Then** 校验失败。
2. **Given** 稳定性不是 `stable`/`preview`/`beta`/`control_plane` 之一，**When** 校验，**Then** 校验失败。
3. **Given** 已发布目录版本，**When** 原地改变已有字段含义（同名字段语义变化）而不升版本，**Then** 兼容策略检查失败；仅允许增补向后兼容字段。

---

### User Story 3 - 稳定允许、预览 opt-in、控制面与未知拒绝 (Priority: P1)

数据面入口必须按目录标签作出统一、可测试的允许/拒绝判定。买家、卖家和管理员都依赖同一套平台错误，而不是各服务自行猜测。

**Why this priority**: 协议兼容基线把“全兼容”定义为目录内转发、目录外拒绝；这是安全与范围边界。

**Independent Test**: 用同一判定函数覆盖 stable 允许、preview 无 opt-in 拒绝、preview 有 opt-in 允许、control-plane 拒绝、未登记拒绝、共享 Project 调用有状态端点拒绝。无需真实上游。

**Acceptance Scenarios**:

1. **Given** 已登记 `stable` 且无状态的端点，**When** 共享或专享 Project 请求该 method/path，**Then** 目录判定为允许转发（本 SF 不执行实际上游调用）。
2. **Given** 已登记 `preview` 或 `beta` 端点且 Project 未 opt-in，**When** 请求该端点，**Then** 拒绝，错误码为 `PREVIEW_NOT_ENABLED`。
3. **Given** 已登记 `preview`/`beta` 且 Project 已对该记录 opt-in，**When** 请求该端点，**Then** 目录判定允许（仍受后续资格与专享规则约束）。
4. **Given** 已登记 `control_plane` 端点（账号、组织、IAM、支付、上游凭据管理等），**When** 请求该路径，**Then** 拒绝，错误码为 `CONTROL_PLANE_NOT_ALLOWED`。
5. **Given** 未出现在目录中的 method/path，**When** 请求，**Then** 拒绝，错误码为 `ENDPOINT_NOT_CATALOGED`。
6. **Given** 目录标记 `stateful=true` 的端点，**When** 共享 Project 请求，**Then** 拒绝，错误码为 `DEDICATED_PROJECT_REQUIRED`；专享 Project 在本 SF 的目录判定中允许（实际绑定在后续 SF 执行）。

---

### User Story 4 - 目录主版本不兼容则失败关闭 (Priority: P1)

Gateway、路由消费者和兼容测试必须在启动时校验自己支持的目录主版本。主版本不匹配时进程不得提供数据面。

**Why this priority**: 防止新旧节点混用不同目录语义导致“同一请求不同判定”。

**Independent Test**: 合法主版本加载成功；人为把消费者声明的主版本改为不兼容值后，加载/启动失败且不处理请求。

**Acceptance Scenarios**:

1. **Given** 目录 `catalog_major` 与消费者声明的支持主版本一致，**When** 进程启动，**Then** 加载成功并锁定该目录版本。
2. **Given** 消费者声明的主版本与目录主版本不一致，**When** 启动或就绪检查，**Then** 失败关闭，不得使用缓存或降级目录继续服务。
3. **Given** 目录文件损坏、无法解析或校验失败，**When** 启动，**Then** 失败关闭。

---

### User Story 5 - 跨服务领域契约成为唯一事实源 (Priority: P2)

Project、Provider Connection、route decision、usage、pricing、ledger、audit 必须有版本化 HTTP 或事件契约及兼容策略，供后续 SF 实现，而不是各服务私自发明字段。

**Why this priority**: 批次 C–G 的实现依赖先行契约；本 SF 不实现这些领域的业务写入。

**Independent Test**: 契约文件存在、可通过 schema/OpenAPI 解析、声明 owner/version/compatibility，并且与目录同样登记在共享契约总表中。

**Acceptance Scenarios**:

1. **Given** 仓库的共享契约根目录，**When** 枚举 V0.2 领域契约，**Then** 至少包含 Project、Provider Connection、route decision、usage、pricing、ledger、audit 的版本化定义。
2. **Given** 任一上述契约，**When** 检查兼容策略，**Then** 已发布版本只允许增补兼容字段；破坏性变更必须新版本并记录弃用窗口。
3. **Given** 账本与额度相关契约，**When** 阅读字段约束，**Then** 金额使用整数最小单位或定点小数，禁止二进制浮点作为金额类型；测试额度不可购买、转让、兑换或提现。

---

### User Story 6 - 人类可读清单可重复生成 (Priority: P2)

文档读者看到的端点清单必须与机器目录同源。生成结果可重复，工作树无非确定性差异。目录变更附带评审记录和兼容影响说明。

**Why this priority**: 防止文档与机器目录漂移，导致发布范围口头化。

**Independent Test**: 连续两次从同一目录生成人类可读清单，字节级一致；改目录后生成物变化可 diff。

**Acceptance Scenarios**:

1. **Given** 同一份已提交目录，**When** 连续两次生成人类可读清单，**Then** 两次输出字节相同。
2. **Given** 目录增加一条 stable 记录，**When** 重新生成，**Then** 清单出现该记录且排序稳定（按 provider、path、method）。
3. **Given** 一次目录变更，**When** 查看冻结/评审记录，**Then** 能找到 schema 校验结果、兼容影响和测试夹具版本说明。

---

### Edge Cases

- 同一 path 模板、不同 HTTP method 视为不同端点。
- 路径变量（`{response_id}`、`{model}`、Vertex resource name）必须使用规范模板，不得为每个资源 ID 展开记录。
- URL 含 `beta` 不足以单独判定为 preview；稳定性以冻结时厂商文档标识加目录评审为准。
- 未知但合法的扩展字段不属于本 SF 的目录记录字段；透传规则由 SF18 约束。目录不得因为未建模扩展字段而拒绝已登记端点。
- 同时匹配更具体模板与通配模板时，使用最长规范 path 模板；禁止模糊多匹配成功。
- 控制面子路径未逐条登记时，已登记控制面前缀不得被当成数据面；未登记的其余路径仍为 `ENDPOINT_NOT_CATALOGED`。
- 目录生成不得依赖本地时区、随机迭代顺序或未排序 map。
- 本 SF 不自动抓取厂商新 API；未进入冻结目录的未来接口保持拒绝。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 提供机器可读、版本化的 Endpoint Catalog 作为三厂商模型数据面的唯一发布清单。
- **FR-002**: 每条目录记录 MUST 包含：`provider`、`protocol_version`、`method`、`path_template`、`stability`、能力标签、`stateful`、`transport`、资源亲和规则、`metering_source`、`first_supported_version`、`test_fixture_version`、官方来源、负责 SF。
- **FR-003**: 目录 MUST 唯一索引 `provider + protocol_version + method + path_template`；重复键 MUST 使校验失败。
- **FR-004**: `stability` MUST 为 `stable`、`preview`、`beta` 或 `control_plane` 之一。
- **FR-005**: 未登记端点 MUST 产生平台错误 `ENDPOINT_NOT_CATALOGED`。
- **FR-006**: 控制面端点 MUST 产生 `CONTROL_PLANE_NOT_ALLOWED`，且不得被代理到厂商账号/组织/IAM/支付/上游凭据管理 API。
- **FR-007**: 共享 Project 请求 `stateful=true` 的端点 MUST 产生 `DEDICATED_PROJECT_REQUIRED`。
- **FR-008**: `preview`/`beta` 端点 MUST 默认拒绝（`PREVIEW_NOT_ENABLED`），仅在记录已登记且 Project opt-in 后允许进入后续资格检查。
- **FR-009**: 人类可读清单 MUST 由机器目录确定性生成，不得手写第二份互相漂移的清单。
- **FR-010**: 目录变更 MUST 经过 schema 校验、评审记录、兼容影响说明和测试夹具版本；已发布版本只增补兼容字段，不原地改变含义。
- **FR-011**: 所有目录消费者启动时 MUST 校验支持的目录主版本；不兼容、损坏或校验失败 MUST 失败关闭。
- **FR-012**: 系统 MUST 发布 Project、Provider Connection、route decision、usage、pricing、ledger、audit 的版本化 HTTP 和/或事件契约及兼容策略。
- **FR-013**: 契约与目录 MUST 登记 owner、语义化版本和兼容/弃用策略。
- **FR-014**: 不得自动抓取并上线厂商新 API；未知未来接口保持未登记拒绝。
- **FR-015**: 不得把 new-api 或任何跨协议转换层登记为 TokenMarket 核心数据面/控制面契约。
- **FR-016**: V0.1 Volcano OpenAI 兼容契约 MUST 保持独立，不并入三厂商冻结目录，也不在本 SF 删除。
- **FR-017**: 每条 `stable` 记录 MUST 能追溯到官方文档、合同测试夹具和负责 SF。
- **FR-018**: 判定函数 MUST 先匹配目录再返回允许或平台错误，不得在本 SF 调用真实厂商。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: Endpoint Catalog 使用 JSON Schema 约束；领域对象使用 OpenAPI 或事件 JSON Schema。事件契约 MUST 含 event ID、type、version、timestamp、payload、producer、correlation ID。平台错误码稳定且可合同测试。已发布契约破坏性变更 MUST 新版本。
- **ER-002 — Security & Privacy**: 控制面与凭据管理路径 MUST 拒绝。契约与夹具 MUST NOT 包含真实密钥、会话或生产数据。Provider Connection 契约不得定义明文回读接口。
- **ER-003 — Data Integrity**: 目录文件是发布范围的事实源；生成物必须可重复。金额相关契约使用整数最小单位或定点小数。账本契约必须表达不可变分录，禁止覆盖/删除原账目的操作形状。
- **ER-004 — Performance & Capacity**: 单次目录加载与判定在测试夹具（不少于冻结日全量记录）上 p95 < 5 ms（本机单元测试量级）；目录加载不得阻塞到网络。本 SF 不承担 500 RPS 压测（属 SF33）。
- **ER-005 — Reliability**: 目录加载失败或主版本不匹配 MUST 失败关闭。进程在成功加载后锁定目录版本；运行中文件被替换不得让在途判定混用两个版本（切换属 SF02，本 SF 提供不可变加载快照）。
- **ER-006 — Observability**: 加载成功必须记录目录主/次版本、记录数、冻结日（无敏感字段）。加载失败必须记录失败原因码。提供目录版本指标标签供后续就绪检查使用。
- **ER-007 — Accessibility**: N/A。本 SF 不交付用户界面。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** 目录文件缺失、JSON 非法或 schema 失败，**When** 消费者启动，**Then** 进程失败关闭，不监听数据面，不使用旧缓存猜测允许集合。
2. **Given** 重复或并发加载同一目录，**When** 判定请求，**Then** 结果幂等且仅依赖加载快照，不出现部分记录可见。
3. **Given** 回滚到上一已发布目录版本（主版本仍兼容），**When** 进程用该版本启动，**Then** 加载成功且判定与该版本记录一致；主版本不兼容的回滚包 MUST 失败关闭而不是 silently 忽略新增字段含义变化。

### Key Entities

- **EndpointCatalog**: 冻结日发布清单。不变量：单一 `catalog_major`；记录键唯一；生成的人类清单同源。分类：公开工程产物，无密钥。保留：随版本库永久可追溯。
- **EndpointRecord**: 单条 method/path。属性见 FR-002。`stateful` 与 `transport` 决定共享/专享与亲和。审计：变更必须有评审记录。
- **CatalogAdmissionDecision**: 对一次 method/path + Project 模式 + preview opt-in 的允许或平台错误。不是路由结果。
- **ProjectContract**: 买家 Project 的身份、模式（`shared`/`dedicated`，创建后不可变）、协议绑定引用。本 SF 只定义契约。
- **ProviderConnectionContract**: 卖家上游连接；凭据只写加密材料引用，禁止明文读回形状。
- **RouteDecisionContract**: 可解释、可重放的选择记录（资格过滤 + 评分版本），本 SF 只定义字段与版本。
- **UsageObservationContract**: 多维 usage 与可选上游花费；不确定费用不得表示为 0。
- **PricingContract**: 版本化费率、买家倍率、卖家报价区间。
- **LedgerEntryContract**: 不可变分录；余额仅能由分录派生。
- **AuditEventContract**: 高风险操作与目录/价格版本变更审计。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 冻结日三厂商稳定数据面端点在目录中的唯一覆盖率为 100%（无重复键，无来源文档点名却缺失的稳定家族）。
- **SC-002**: 针对缺稳定性、状态性、传输、计量或测试夹具的负向夹具，校验拒绝率为 100%。
- **SC-003**: stable 允许、preview 默认拒绝、preview opt-in 允许、control-plane 拒绝、未登记拒绝、共享+有状态拒绝各至少有一条自动测试且通过。
- **SC-004**: 人为制造目录主版本不兼容时，消费者启动失败率为 100%，且失败后不接受数据面判定请求。
- **SC-005**: 连续两次生成人类可读清单的字节差异为 0。
- **SC-006**: 每条 stable 记录都能在不超过一次目录查询内定位到官方来源、夹具版本和负责 SF。
- **SC-007**: Project / Provider Connection / route decision / usage / pricing / ledger / audit 契约均可被机器解析，并出现在共享契约总表中。

## Assumptions

- 发布冻结日为 2026-08-31；官方来源以该日可引用的厂商公开文档为准。厂商文档含糊或不稳定的接口不进入 `stable`。
- V0.2 买家数据面仅 OpenAI、Anthropic、Google Vertex；V0.1 Volcano 适配器继续服务既有契约，但不进入本目录。
- 本 SF 不实现代理转发、真实上游调用、Project CRUD、账本过账或 UI。
- 真实厂商付费冒烟、独立渗透不在本 SF 范围；未授权前保持为后续发布阻塞项。
- 控制面示例至少覆盖：OpenAI organization/admin/usage/billing/API key 管理；Anthropic Admin/组织/API key；Vertex IAM/项目/计费/自定义 endpoint 管理。
- Preview 示例至少各厂商一条已登记但不默认开放的记录。
- 合同测试夹具可以是最小 JSON 请求/响应样本；全量协议差分属于 SF19–SF21。
- 目录消费者包括：proxy-gateway、api-service、billing-service、admin-service 以及仓库级契约测试。
