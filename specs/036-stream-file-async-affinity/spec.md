# Feature Specification: SSE、WebSocket、文件与异步资源亲和

**Feature Branch**: `036-stream-file-async-affinity`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 SSE、WebSocket、文件与异步资源亲和"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF22-SSEWebSocket文件与异步资源亲和.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 共享 vs 专享？ → A: 目录 `stateful=true` 或 `affinity=resource_id|connection` 的端点仅 dedicated；共享模式继续被目录 `DEDICATED_PROJECT_REQUIRED` 拒绝。
- Q: 亲和缺失？ → A: 查询/取消/下载/删除若无映射或映射冲突，平台错误 fail-closed，不得另选连接。
- Q: 更换专享连接？ → A: 不迁移既有厂商资源；旧 resource ID 仍指向原 Connection，原连接不可用则失败关闭。
- Q: 流式与上传？ → A: SSE 不整包缓冲，保事件顺序；慢客户端 idle timeout；multipart/二进制不落盘明文临时文件；超限在读完整正文前终止。
- Q: 500×2h soak？ → A: 内核提供可扩展 soak 夹具。CI 跑短时并发证明无无界缓存；全量 500/2h 由环境变量启用（SF33/发布门禁复用），本 SF 不得用 mock 替代亲和 fail-closed 行为。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - SSE 背压与取消 (Priority: P1)

长响应按事件刷新，慢客户端超时，取消传播，不拖垮其它请求。

**Why this priority**: 长连接是数据面容量与正确性的基础。

**Independent Test**: 多事件顺序；阻塞 writer 触发 idle；取消到达 upstream。

**Acceptance Scenarios**:

1. **Given** SSE 上游依次发送 event a,b,c，**When** 透传，**Then** 客户端按相同顺序收到且无需等流结束才 flush。
2. **Given** 客户端停止读取，**When** idle 超时，**Then** 代理结束该流且其它请求仍成功。
3. **Given** 客户端取消，**When** SSE 进行中，**Then** 1 秒内 upstream 看到取消。

---

### User Story 2 - WebSocket 固定连接 (Priority: P1)

握手与双向字节原样转发；建立后固定 Connection。

**Independent Test**: Upgrade 头转发；101 后回显帧；shared 模式拒绝 stateful WS。

**Acceptance Scenarios**:

1. **Given** dedicated + catalog websocket 端点，**When** Upgrade，**Then** upstream 收到 Upgrade/Connection 并返回 101。
2. **Given** shared Project，**When** 请求同一 stateful WS 端点，**Then** `DEDICATED_PROJECT_REQUIRED`。

---

### User Story 3 - 上传限制与无明文落盘 (Priority: P1)

超限上传在读完前终止；内核不以明文临时文件缓冲。

**Independent Test**: Content-Length 超限不转发；源码无 CreateTemp 明文缓冲。

**Acceptance Scenarios**:

1. **Given** multipart 超限，**When** POST files，**Then** 413 且 upstream 未收满正文。
2. **Given** passthrough/affinity 包，**When** 扫描，**Then** 无 os.CreateTemp / 明文临时路径。

---

### User Story 4 - 资源亲和 fail-closed (Priority: P1)

创建响应登记 resource ID→Connection；后续请求必须打回原连接；缺失不重路由。

**Independent Test**: 创建后 GET 使用同一 ConnectionID；未知 ID 返回 AFFINITY_NOT_FOUND。

**Acceptance Scenarios**:

1. **Given** POST `/v1/files` 返回 `{"id":"file-1"}`，**When** GET `/v1/files/file-1`，**Then** Selector 使用创建时的 ConnectionID。
2. **Given** 无映射，**When** GET `/v1/files/missing`，**Then** `AFFINITY_NOT_FOUND`，且 Select 不被调用为随机其它连接。
3. **Given** 映射指向 conn-A，**When** 节点仅用内存重启前已持久化的映射，**Then** 仍解析到 conn-A。

---

### Edge Cases

- 人工更换 dedicated Connection 后，旧 resource ID 不自动改绑。
- 计量：同一 request_id 结束事件幂等，重连不重复结算。
- 全量 500 连接 × 2 小时 soak 由 `TOKENMARKET_SOAK_*` 启用；默认 CI 短时并发。

## Requirements *(mandatory)*

- **FR-001**: SSE MUST 流式转发、保序、支持 idle timeout 与取消。
- **FR-002**: WebSocket MUST 转发握手与后续字节；建立后固定 Connection。
- **FR-003**: 上传下载 MUST 流式、限大小、不落盘明文临时文件。
- **FR-004**: 创建响应 MUST 登记 resource→Connection/Project 亲和。
- **FR-005**: 后续资源操作 MUST 按亲和解析；缺失/冲突 fail-closed。
- **FR-006**: 共享模式 MUST 不能使用 stateful/affinity 端点。
- **FR-007**: 计量结束事件 MUST 幂等。

### Engineering Requirements

- **ER-001**: 扩展 `native-passthrough/v1` 至 1.1.0（affinity/transport）。
- **ER-002**: 领域包 affinity + kernel 传输分支。
- **ER-003**: 覆盖率 ≥80%；负向亲和与上传截断测试。

## Success Criteria

- **SC-001**: 资源后续请求打到原 Connection 的比例 100%。
- **SC-002**: 缺失映射被重路由的次数 = 0。
- **SC-003**: 超限上传完整转发次数 = 0。
- **SC-004**: SSE 事件乱序次数 = 0。
- **SC-005**: 明文临时文件路径数 = 0。

## Assumptions

- Selector.SelectConnection 由测试/SF23 提供；本 SF 实现亲和解析与固定。
- 全量 soak 时长由发布门禁/SF33 调度，本 SF 交付夹具与短时证明。
