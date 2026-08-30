# Feature Specification: 代理网关无状态化与水平扩展

**Feature Branch**: `021-gateway-stateless-scale`

**Created**: 2026-08-31

**Status**: Implemented

**Input**: User description: "V0.2 代理网关无状态化与水平扩展：不可变配置快照、原子切换、摘流与失败关闭"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF02-代理网关无状态化与水平扩展.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 本地用量 WAL 是否仍可作为唯一副本？ → A: 否。本地文件只允许作可丢弃缓存；用量事实必须可在无本地文件时继续（远程 sink 或后续 Outbox/SF04）。
- Q: 路由占用/会话唯一状态？ → A: 本 SF 不得把它们当作节点私有事实源；进程内 inflight 仅为可重建缓存。跨节点协调属 SF03。
- Q: 配置切换语义？ → A: 目录与运行配置组成不可变版本；请求进入时锁定，不得混用两个版本字段。
- Q: 压测 3 节点终止 0.1% 失败？ → A: 本 SF 交付可重复的多实例行为一致与摘流单元/集成测试；500 RPS 节点杀死属 SF33，但本 SF 必须提供摘流与无本地恢复的可执行证明。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 不可变快照与原子切换 (Priority: P1)

运行配置与 Endpoint Catalog 以不可变版本加载。切换时在途请求继续使用进入时锁定的完整快照，新请求使用新快照。不得出现“目录是新的、限流配置是旧的”的混合字段。

**Why this priority**: 水平扩展的前提是任一节点对同一版本行为一致。

**Independent Test**: 并发请求期间切换快照，断言每个请求的判定只引用一个 version id。

**Acceptance Scenarios**:

1. **Given** 已加载 version=1 的快照，**When** 原子切换到 version=2，**Then** 切换前已进入的请求仍只读 version=1 字段。
2. **Given** 切换完成，**When** 新请求进入，**Then** 只读 version=2。
3. **Given** 损坏或不兼容目录，**When** 尝试切换，**Then** 切换失败且继续使用原快照，或启动场景失败关闭。

---

### User Story 2 - 无本地唯一事实即可重启 (Priority: P1)

Gateway 节点重启后不依赖本机用量 WAL、会话文件或占用表即可处理已存在的 Project/Key（授权与目录来自共享契约/远程事实）。本地内存丢失不得造成账务唯一副本丢失。

**Why this priority**: 验收“重启全部 Gateway 后无需恢复本地文件”。

**Independent Test**: 启用本地 WAL 缓存写入后删除目录并重启加载器，进程仍能加载目录并生成用量事件到远程 sink；不得要求回放本地文件才能启动。

**Acceptance Scenarios**:

1. **Given** 节点曾写入本地用量缓存文件，**When** 删除这些文件并启动，**Then** 启动成功（目录主版本匹配）且可接受健康检查。
2. **Given** 远程用量 sink 不可用且无其他持久路径，**When** 尝试把本地文件当作唯一副本，**Then** 该路径不得被实现为成功账务提交。
3. **Given** 进程内 inflight 占用在崩溃后清零，**When** 新进程启动，**Then** 占用表为空（可重建缓存），不从磁盘恢复占用。

---

### User Story 3 - 摘流与有界排空 (Priority: P1)

摘流后不接收新请求；在途非流式请求在期限内完成或返回确定错误；长连接有界排空。liveness 在摘流期间仍可 alive，readiness 变为 not ready。

**Why this priority**: 滚动发布与节点终止的安全前提。

**Independent Test**: 挂起一个在途请求，调用 Drain，新请求被拒绝；在途完成后或超时后 Drain 返回。

**Acceptance Scenarios**:

1. **Given** 节点 serving，**When** Drain 开始，**Then** readiness 非 ready，新代理请求被拒绝（确定错误），liveness 仍 alive。
2. **Given** 在途非流式请求，**When** Drain 且在期限内完成，**Then** 该请求正常结束。
3. **Given** 在途请求超过排空期限，**When** Drain 截止，**Then** 返回确定错误且不再无限等待。

---

### User Story 4 - 多实例行为一致与脱敏 (Priority: P2)

同一合法 Key 打到任一健康节点，目录判定与错误码一致。日志/指标不含 upstream 密钥、验证码、完整请求正文。

**Why this priority**: 水平扩展用户可观察的一致性与安全。

**Independent Test**: 两个独立 Snapshot 副本对同一 method/path 产生相同 Admit 结果；脱敏测试扫描日志。

**Acceptance Scenarios**:

1. **Given** 两份相同快照，**When** 对同一请求做目录判定，**Then** 允许/错误码完全一致。
2. **Given** 代理处理含 Authorization 的请求，**When** 检查结构化日志，**Then** 不含密钥明文或完整消息正文。

---

### Edge Cases

- 快照切换与 Drain 同时发生：已进入请求保持进入时快照直到结束或超时。
- 共享依赖（目录）不可用：启动失败关闭；运行中切换失败保留旧快照。
- Gateway 不提供用户管理、改价或人工账务 API。
- 本 SF 不实现 Redis 占用表（SF03）和 Outbox（SF04），但不得把本地 WAL/占用文件定义成事实源。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Gateway MUST 仅将本地内存用于可重建缓存，不得将会话、额度、路由占用或用量事件的唯一副本放在节点磁盘或仅内存队列。
- **FR-002**: 每个数据面请求 MUST 在入口锁定一个完整运行快照（含目录版本）。
- **FR-003**: 配置/目录切换 MUST 原子发布新快照；禁止请求混用两个版本的字段。
- **FR-004**: readiness MUST 在目录未锁定或正在摘流时失败；liveness MUST 不因短暂 upstream 错误失败。
- **FR-005**: Drain MUST 拒绝新请求并有界等待在途请求。
- **FR-006**: 重启 MUST NOT 要求恢复本地用量/占用文件。
- **FR-007**: 相同快照下目录判定 MUST 在节点间一致。
- **FR-008**: 日志与指标 MUST NOT 包含 upstream 密钥、验证码或完整请求/响应正文。
- **FR-009**: 共享依赖无法安全判定权限/路由时 MUST 失败关闭，不得凭过期缓存放行未登记端点。
- **FR-010**: Gateway MUST NOT 承载用户管理、价格编辑或人工账务操作。

### Engineering Requirements *(mandatory)*

- **ER-001 — Contracts**: 快照含 `catalog_major`/`snapshot_id`；Drain 拒绝使用稳定平台错误或 503 `NOT_READY`。
- **ER-002 — Security & Privacy**: 沿用现有脱敏；本 SF 不新增密钥落盘。
- **ER-003 — Data Integrity**: 用量事件生成不得以本地 WAL 成功当作入账成功。
- **ER-004 — Performance & Capacity**: 快照 Pin/Unpin 与切换在单测中正确；500 RPS 证明属 SF33。
- **ER-005 — Reliability**: Drain 超时必须结束；切换失败可保留旧版本。
- **ER-006 — Observability**: 记录 snapshot_id、catalog_major、drain 状态。
- **ER-007 — Accessibility**: N/A（无 UI）。

### Failure and Recovery Scenarios *(mandatory)*

1. **Given** 目录加载失败，**When** 启动，**Then** 进程失败关闭。
2. **Given** 并发切换与请求，**When** 判定，**Then** 每个请求只见一个完整快照。
3. **Given** Drain 超时，**When** 排空截止，**Then** 在途请求得到确定错误，进程可退出。

### Key Entities

- **RuntimeSnapshot**: 不可变；含 snapshot_id、catalog、生成单调版本。
- **SnapshotPin**: 请求持有的快照租约。
- **DrainState**: serving / draining / stopped。

## Success Criteria *(mandatory)*

- **SC-001**: 并发切换测试中 100% 请求只绑定一个 snapshot_id。
- **SC-002**: 删除本地用量文件后启动成功率 100%（目录合法时）。
- **SC-003**: Drain 开始后新请求拒绝率 100%，liveness 仍 200。
- **SC-004**: 两副本快照对同一输入 Admit 一致率 100%。
- **SC-005**: 脱敏扫描在本 SF 覆盖的日志夹具中密钥泄漏为 0。

## Assumptions

- SF01 目录加载器已存在。
- 跨节点 Redis 占用属 SF03；可靠 Outbox 属 SF04。
- 三节点真实压测杀死属 SF33，本 SF 提供机制与单机可重复证明。
