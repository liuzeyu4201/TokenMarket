# 任务：火山方舟请求与响应兼容

**输入**: 设计文档来自 `/specs/007-volcano-openai-compat/`

**前置**: `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`

**语言**: 任务描述与备注默认简体中文；标识符、路径、API 字段、环境变量、枚举保持原文。

**测试**: 每次行为变更均 **必须** 先写测试并在实现前观察到失败。`services/proxy-gateway/internal/domain/chatcompat/` 与 volcano chat/SSE 相关包要求 ≥80% 行覆盖率；允许列表拒绝、usage 禁止假 0、流式失败分界、60s 截止、生成不重试、脱敏须直接断言。

**组织**: 按用户故事分组。Setup + Foundational 阻塞全部故事。

| 故事 | 优先级 | MVP? | 内容 |
|------|--------|------|------|
| US1 | P1 | **是** | 非流式：允许列表过滤 + 模型映射 + `POST /chat/completions` + 兼容响应；content 原样；usage 缺失仍 success |
| US2 | P1 | 建议同批 | SSE 增量解析、顺序、唯一 `[DONE]`、拆包/合包 |
| US3 | P2 | 其后 | 稳定失败分类、60s 截止、取消、生成不重试、流式零事件 vs 已出事件分界、脱敏 |

**MVP 范围**: Phase 1–3（US1）。可交付适配建议 **US1+US2+US3**。

**明确不在任务内**: 公开 `POST /v1/proxy/...`（SF12/SF15）、买家认证、卖家 Key 选择、用量落账（SF17）、内部 HTTP 路由（research D1）、多平台、真实火山默认 CI、生成自动重试、官方 SDK。

## 格式：`[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件，同批次无未完成依赖）
- **[Story]**: `[US1]` / `[US2]` / `[US3]` 仅用于故事阶段
- 每个任务须包含精确文件路径

## 路径约定

- Gateway: `services/proxy-gateway/`
- 特性契约源: `specs/007-volcano-openai-compat/contracts/`
- 共享契约（实现时）: `shared/contracts/volcano-openai-compat/v1/`
- 领域: `services/proxy-gateway/internal/domain/chatcompat/`
- 应用: `services/proxy-gateway/internal/application/`
- 适配: `services/proxy-gateway/internal/infrastructure/platform/volcano/`
- 观测: `services/proxy-gateway/internal/observability/`
- 测试: 与包同目录 `*_test.go`（Go 惯例）

---

## Phase 1: Setup（共享基础设施）

**目的**: 提升契约、包骨架、配置占位；尚无 chat 业务行为。

- [x] T001 将特性契约提升至 `shared/contracts/volcano-openai-compat/v1/`：复制 `specs/007-volcano-openai-compat/contracts/` 下全部文件（`volcano-openai-compat.openapi.yaml`、`error-classification.md`、`request-field-allowlist.md`、`header-allowlist.md`、`sse-events.md`、`usage-observation.md`、`upstream-volcano-chat.md`、`consumer-notes.md`），并在 `shared/contracts/README.md` 登记所有权/版本；**不得**修改 `shared/contracts/volcano-key-validation/v1/` 破坏性字段
- [x] T002 [P] 在 `services/proxy-gateway/README.md` 增加 volcano-openai-compat v1 契约索引，并写明 V0.1 为同进程端口、**不**挂载公开/内部 HTTP
- [x] T003 [P] 创建包骨架（可编译空文件/包注释）：`services/proxy-gateway/internal/domain/chatcompat/`、`services/proxy-gateway/internal/infrastructure/platform/volcano/chat_client.go`、`services/proxy-gateway/internal/infrastructure/platform/volcano/sse.go`、`services/proxy-gateway/internal/infrastructure/platform/volcano/fixtures/`、`services/proxy-gateway/internal/observability/chat_metrics.go`
- [x] T004 [P] 在 `services/proxy-gateway/internal/domain/chatcompat/contract_assets_test.go` 添加契约资产存在/OpenAPI YAML 可解析冒烟测试，指向 `shared/contracts/volcano-openai-compat/v1/`
- [x] T005 [P] 在仓库根 `.env.example` 文档化占位（无真实密钥）：`VOLCANO_CHAT_BASE_URL`（可注明默认复用 `VOLCANO_VALIDATE_BASE_URL`）、`VOLCANO_CHAT_DEFAULT_DEADLINE_SECONDS`（60）、`VOLCANO_CHAT_MAX_DEADLINE_SECONDS`（300）、`VOLCANO_CHAT_MAX_BODY_BYTES`（2097152）、`VOLCANO_CHAT_MODEL_MAP`、`VOLCANO_V01_CHAT_MODELS`（已有则交叉引用）；注释标明生成请求禁止自动重试

**检查点**: 契约可发现；空包存在；无 chat 出站行为。

---

## Phase 2: Foundational（阻塞性前置）

**目的**: 领域类型、允许列表、usage 不变量、模型映射、配置、金标；阻塞全部用户故事。

**关键**: 本阶段完成前不得开始 US1–US3 出站编排。先写 foundational 测试并观察到失败。

- [x] T006 [P] 在 `services/proxy-gateway/internal/domain/chatcompat/types_test.go` 添加失败测试：`ChatAdaptRequest`/`ChatAdaptResult`/`StreamEvent` 与 `error_category` 枚举全集对齐 `shared/contracts/volcano-openai-compat/v1/error-classification.md`（含 `unsupported_parameter`、`unsupported_endpoint`、`truncated_stream`）
- [x] T007 [P] 在 `services/proxy-gateway/internal/domain/chatcompat/allowlist_test.go` 添加失败测试：扩展采样集合法；`tools`/`response_format`/`n=2`/未知顶层键 → `unsupported_parameter`；`messages[].content` 为 text parts 或含 `image_url` **不得**被拒绝；消息级 `tool_calls`/`name` 拒绝
- [x] T008 [P] 在 `services/proxy-gateway/internal/domain/chatcompat/usage_test.go` 添加失败测试：三分项自洽 → `complete`；缺失 → `missing` 且不得出现全 0 对象；`total < prompt+completion` → `inconsistent` 且不改写数值
- [x] T009 [P] 在 `services/proxy-gateway/internal/domain/chatcompat/modelmap_test.go` 添加失败测试：默认恒等；`VOLCANO_CHAT_MODEL_MAP` 覆盖；未知公开模型 → `unsupported_parameter`；响应回写公开 ID
- [x] T010 在 `services/proxy-gateway/internal/domain/chatcompat/types.go` 实现请求/结果/流事件类型与枚举（`error_category`/`usage_status`/`kind`/`suggested_action`），直至 T006 通过
- [x] T011 在 `services/proxy-gateway/internal/domain/chatcompat/allowlist.go` 实现顶层字段过滤与取值校验（不静默钳制），直至 T007 通过
- [x] T012 在 `services/proxy-gateway/internal/domain/chatcompat/usage.go` 实现 usage 完整性判定（禁止假 0），直至 T008 通过
- [x] T013 在 `services/proxy-gateway/internal/domain/chatcompat/modelmap.go` 实现公开↔上游映射（allowlist 对齐 `VOLCANO_V01_CHAT_MODELS`），直至 T009 通过
- [x] T014 在 `services/proxy-gateway/internal/domain/chatcompat/config.go` 定义 chat 配置：base URL、默认截止 60s、最大截止 300s、max body 2MiB、模型 map；从环境加载；空 allowlist fail-closed
- [x] T015 [P] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/fixtures/` 添加合成金标：非流式成功、无 `choices`、无 `usage`、畸形 JSON；**禁止**真实 Key 与真实用户正文
- [x] T016 [P] 在 `services/proxy-gateway/internal/domain/chatcompat/classify.go` 包装 `providervalid` 的 HTTP/传输映射，并增加 chat 特有类别；429 复用 `retry_after` 默认 5 / 钳制 300

**检查点**: 类型/允许列表/usage/映射可单测；fixture 金标就位。

---

## Phase 3: User Story 1 - 转换非流式聊天请求与响应 (Priority: P1) 🎯 MVP

**目标**: 同进程可完成允许列表过滤、模型映射、一次非流式出站、兼容响应标准化；content 原样；usage 缺失仍 `success`。

**独立测试**: httptest 200 + choices；默认 usage 完整或缺失；未声明顶层键不出站；`image_url` content 不被拒绝。

### User Story 1 的测试（先写并观察到失败）

- [x] T017 [P] [US1] 在 `services/proxy-gateway/internal/domain/chatcompat/filter_request_test.go` 添加：合法扩展采样集产出出站 JSON 仅含允许键；未知顶层键失败且不进入 client
- [x] T018 [P] [US1] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/chat_client_test.go` 添加：httptest `POST /chat/completions` 200 解析 `choices`；出站 `Authorization`/`Content-Type`/`Accept` 仅为允许列表；请求体不含买家头
- [x] T019 [P] [US1] 在 `services/proxy-gateway/internal/domain/chatcompat/normalize_response_test.go` 添加：无 `choices` → `invalid_response`；有 `choices` 无 usage → `success` + `usage_status=missing`；`total` 不自洽 → `success` + `inconsistent`；`model` 回写公开 ID
- [x] T020 [P] [US1] 在 `services/proxy-gateway/internal/application/chat_completions_test.go` 添加编排：合法请求 → 上游 1 次 POST → 兼容成功对象；`platform=openai` → `unsupported_platform` 且上游调用 0；`endpoint` 非 chat → `unsupported_endpoint`
- [x] T021 [P] [US1] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/chat_client_test.go`（或独立 `headers_test.go`）添加：不得转发 `Cookie`/`X-Internal-Token`/买家 `Authorization`
- [x] T022 [P] [US1] 在 `services/proxy-gateway/internal/domain/chatcompat/allowlist_test.go` 扩展：`content` 为 `[{type:text,...},{type:image_url,...}]` 的请求过滤成功

### User Story 1 的实现

- [x] T023 [US1] 在 `services/proxy-gateway/internal/domain/chatcompat/response.go` 实现非流式响应标准化（choices / usage_status / 公开 model），直至 T019 通过
- [x] T024 [US1] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/chat_client.go` 实现非流式 `POST {base}/chat/completions`（context 取消、Bearer、头允许列表、解析 fixtures 形状），直至 T018/T021 通过
- [x] T025 [US1] 在 `services/proxy-gateway/internal/application/chat_completions.go` 实现非流式编排（platform/endpoint 检查 → 允许列表 → 模型映射 → 出站 → 标准化），**禁止自动重试**，直至 T020 通过
- [x] T026 [US1] 将 T017/T022 过滤接到 `chat_completions.go` 出站前，确保失败路径不调用 `ChatClient`
- [x] T027 [US1] 重跑 US1 相关 `go test` 至绿；确认 `chatcompat` 与 volcano chat 非流式路径覆盖率可统计

**检查点**: MVP — 非流式内部适配可演示兼容成功与参数拒绝。

---

## Phase 4: User Story 2 - 转换流式事件 (Priority: P1)

**目标**: 增量 SSE 解析保持顺序与 delta 语义；正常结束唯一 `[DONE]`；拆包/合包/注释/半个字符不产出损坏 JSON。

**独立测试**: 多块/拆包/合包/末块 usage 的受控字节流；不 `ReadAll` 全响应。

### User Story 2 的测试（先写并观察到失败）

- [x] T028 [P] [US2] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/sse_test.go` 添加：同一逻辑事件跨两个 `Write` 分块后才 yield；一块含两个完整事件则两次 yield
- [x] T029 [US2] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/sse_test.go` 扩展：注释行、空行、多行 `data:` 拼接；未知 `event:` 忽略（与 T028 同文件，勿并行）
- [x] T030 [P] [US2] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/sse_utf8_test.go` 添加：半个 UTF-8 码点跨块不产出损坏 JSON
- [x] T031 [P] [US2] 在 `services/proxy-gateway/internal/application/chat_completions_stream_test.go` 添加：上游 delta 顺序保持；正常结束只发出一次 `kind=done`（契约 `[DONE]`）；末块 usage 可缺失仍 done

### User Story 2 的实现

- [x] T032 [US2] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/sse.go` 实现增量分帧解析器（禁止为解析而读完整 body），直至 T028–T030 通过
- [x] T033 [US2] 扩展 `services/proxy-gateway/internal/infrastructure/platform/volcano/chat_client.go`：`stream=true` 时 `Accept: text/event-stream` 并返回事件迭代
- [x] T034 [US2] 扩展 `services/proxy-gateway/internal/application/chat_completions.go`（或 `chat_completions_stream.go`）将 chunk 标准化为 `StreamEvent`（公开 model、delta 语义），直至 T031 通过
- [x] T035 [US2] 重跑 US2 测试至绿；断言测试替身使用流式读取而非 `io.ReadAll` 全响应（SC-002 **CI 红线**：禁止聚合完整流）
- [x] T059 [US2] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/sse_scale_test.go` 添加 **CI 红线** 测试：内存确定性生成 ≥10_000 个多样化 SSE 事件（须含拆包、合包、注释行、一次正常 `[DONE]`），断言 yield 计数匹配、顺序稳定、零重复、恰好一次 `kind=done`、无补造终止（SC-005）

**检查点**: 流式事件转换可独立验收（含 10k 计数门禁）。

---

## Phase 5: User Story 3 - 稳定映射上游失败 (Priority: P2)

**目标**: 401/403/429/5xx/超时/非法响应稳定分类；默认 60s 硬截止；生成不重试；流式按已交出事件分界；全程脱敏。

**独立测试**: 表驱动状态码；429 无 Retry-After → 5；零事件 401 vs 已出 delta 后 EOF。

### User Story 3 的测试（先写并观察到失败）

- [x] T036 [P] [US3] 在 `services/proxy-gateway/internal/domain/chatcompat/classify_table_test.go` 添加全量分类表驱动：对齐 `error-classification.md` 与 SC-004
- [x] T037 [P] [US3] 在 `services/proxy-gateway/internal/domain/chatcompat/retry_after_test.go` 添加：`Retry-After` 秒/HTTP-date；缺失→5；超过 max→钳制 300；`rate_limited` 字段必填
- [x] T038 [P] [US3] 在 `services/proxy-gateway/internal/application/chat_stream_boundary_test.go` 添加：尚未 yield 时上游 401 → 结构化 `invalid`、无 `done`、无空流；yield ≥1 后断开 → `truncated_stream`、不补 `[DONE]`、不插入错误 JSON
- [x] T039 [P] [US3] 在 `services/proxy-gateway/internal/application/chat_deadline_test.go` 添加：无调用方截止且上游阻塞 → ≤60s `timeout`；更短 caller deadline 优先
- [x] T040 [P] [US3] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/chat_client_retry_test.go` 添加：5xx/瞬时错误 **不得**重试，上游调用次数 = 1
- [x] T041 [P] [US3] 在 `services/proxy-gateway/internal/domain/chatcompat/redaction_leak_test.go` 添加：含 Key/正文的上游错误包装后，对外结果与日志无明文 Key、无 messages 正文（SC-006）
- [x] T042 [P] [US3] 在 `services/proxy-gateway/internal/application/chat_completions_test.go` 扩展：caller 100ms 取消；零事件不 success；已出事件走 truncated

### User Story 3 的实现

- [x] T043 [US3] 扩展 `services/proxy-gateway/internal/domain/chatcompat/classify.go` 与 retry_after 接线，直至 T036–T037 通过
- [x] T044 [US3] 在 `services/proxy-gateway/internal/application/chat_completions.go`（及 stream 路径）落实 FR-016 分界，直至 T038 通过
- [x] T045 [US3] 在 `services/proxy-gateway/internal/application/chat_completions.go` 强制 `min(caller, default 60s)` 并钳制 max 300s，直至 T039 通过
- [x] T046 [US3] 确保 `services/proxy-gateway/internal/infrastructure/platform/volcano/chat_client.go` 生成路径 `MaxAttempts=1`，直至 T040 通过
- [x] T047 [US3] 在 `services/proxy-gateway/internal/domain/chatcompat/redaction.go`（可复用 `providervalid` 哈希）强化脱敏，直至 T041 通过
- [x] T048 [US3] 重跑 US3 与相关 `go test ./... -count=1 -race` 至绿

**检查点**: 失败分类、截止、截断分界可独立验收；无 Key 泄漏。

---

## Phase 6: Polish & Cross-Cutting Concerns

**目的**: 可观测性闭环、契约对齐、quickstart、覆盖率与安全扫描。

- [x] T049 [P] 在 `services/proxy-gateway/internal/observability/chat_metrics.go` 与 `services/proxy-gateway/internal/application/chat_completions.go` 接线真实指标与结构化日志（platform、stream、error_category、duration、request_id、credential_ref；无 Key/正文）
- [x] T050 [P] 新增 `ops/runbooks/volcano-openai-compat.md`：`invalid_response` 与 `truncated_stream` 分诊、官方契约变化 vs 网络截断、禁止把截断当永久 invalid
- [x] T051 按 `specs/007-volcano-openai-compat/quickstart.md` 跑通替身验收并记录命令结果摘要到 `specs/007-volcano-openai-compat/evidence/`
- [x] T060 在 `services/proxy-gateway/internal/domain/chatcompat/` 或 `internal/application/` 增加 `go test -bench`（非流式转换不含上游等待、单事件转换）；将输出与环境（OS/CPU/`GOMAXPROCS`）写入 `specs/007-volcano-openai-compat/evidence/`。目标对照 SC-002 的 5 ms / 1 ms；**不得**把该墙钟阈值加进默认 CI fail 条件（SC-002 证据层）
- [x] T052 复核 `shared/contracts/volcano-openai-compat/v1/upstream-volcano-chat.md`：用当期官方文档更新复核记录表；确认仍为 `POST /api/v3/chat/completions` + Bearer + SSE `[DONE]`
- [x] T053 运行 `cd services/proxy-gateway && go test ./internal/domain/chatcompat/ ./internal/infrastructure/platform/volcano/ ./internal/application/ -cover -count=1`：`chatcompat` 与 volcano chat/SSE 路径 ≥80% 行；分类、usage、分界、脱敏直接覆盖
- [x] T054 [P] 运行仓库 `make lint` / `make test`（或 gateway 目标）与 `make security-check`（若可用）：确认无真实 Key 入仓、夹具仅合成
- [x] T055 [P] 更新 `services/proxy-gateway/README.md`：如何从同进程调用 `ChatCompletions`、环境变量、禁止生成重试、禁止 usage 填 0
- [x] T056 对照 `shared/contracts/volcano-openai-compat/v1/volcano-openai-compat.openapi.yaml` 做结果字段最终对齐检查
- [x] T057 [P] 在 `services/proxy-gateway/internal/domain/chatcompat/consumer_notes_doc_test.go` 添加轻量断言：`consumer-notes.md` 存在且声明临时类/`truncated_stream` 不得写永久 invalid
- [x] T058 [P] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/sse_fuzz_test.go` 添加模糊测试：随机分块/非法 UTF-8/超长行不得 panic

**检查点**: 可合并；quickstart 可复现；契约与实现一致。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: 无依赖，立即开始
- **Phase 2 Foundational**: 依赖 Phase 1；**阻塞**全部用户故事
- **Phase 3 US1**: 依赖 Phase 2 → MVP
- **Phase 4 US2**: 依赖 Phase 2；application 流式接线依赖 US1 的 `ChatClient` 骨架（T024）；T059 依赖 T032
- **Phase 5 US3**: 依赖 US1 出站；流式分界（T038/T044）依赖 US2 解析器（T032）
- **Phase 6 Polish**: 依赖目标故事完成

### User Story Dependencies

- **US1 (P1)**: Foundational 后即可；无其他故事依赖
- **US2 (P1)**: 解析器文件独立，可与 US1 后期并行；端到端 stream 编排需 US1 client
- **US3 (P2)**: 分类表可独立测；截断分界需 US2 yield 计数

### Within Each Story

1. 测试先写并失败  
2. 实现至测试绿  
3. 故事检查点再进入下一优先级  

### Parallel Opportunities

- Phase 1：T002–T005 可并行  
- Phase 2：T006–T009、T015–T016 可并行  
- US1 测试：T017–T022 可并行  
- US2 测试：T028–T031 可并行  
- US3 测试：T036–T042 可并行  
- Polish：T049/T050/T055/T057/T058 可并行  

---

## Parallel Example: User Story 1

```bash
# 并行启动 US1 测试（不同文件）：
Task: T017 filter_request_test.go
Task: T018 chat_client_test.go
Task: T019 normalize_response_test.go
Task: T020 chat_completions_test.go

# 实现顺序（有依赖）：
T023 response.go → T024 chat_client.go → T025/T026 ChatCompletions
```

## Parallel Example: User Story 2

```bash
Task: T028 sse_test.go 拆包合包
Task: T030 sse_utf8_test.go
Task: T031 chat_completions_stream_test.go
```

---

## Implementation Strategy

### MVP First（仅 US1）

1. Phase 1 Setup  
2. Phase 2 Foundational  
3. Phase 3 US1  
4. **STOP**：用 mock 演示非流式兼容成功 + 参数拒绝 + usage 缺失不填 0  
5. 再合入 US2/US3  

### Incremental Delivery

1. Setup + Foundational → 基础就绪  
2. US1 → 非流式适配 MVP  
3. US2 → 流式事件  
4. US3 → 生产级分类、截止、截断分界  
5. Polish → 可合并证据  

### Parallel Team Strategy

1. 全员完成 Setup + Foundational  
2. Dev A：US1 非流式编排  
3. Dev B：US2 SSE 解析（`sse.go` 独立）  
4. Dev C：US3 分类表（与 A 协调 `classify.go`）  

---

## Notes

- [P] = 不同文件且无未完成依赖  
- 默认 **不挂 HTTP**；SF12/SF15 再接线公开路径  
- usage 缺失不得填 0，不得把成功对象改成 `invalid_response`  
- 生成请求禁止自动重试  
- 真实火山仅可选人工 smoke，不进默认 CI  
- 每完成一逻辑组建议 Conventional Commit（如 `feat(gateway): add volcano chat client`）  
- 下一命令：`/speckit-implement` 或按 Phase 执行  

## Format Validation

- 全部任务以 `- [ ]` 开头  
- 全部含 Task ID（T001–T060；T059=SC-005 CI 10k，T060=SC-002 bench 证据）  
- 故事阶段任务均含 `[US1]`/`[US2]`/`[US3]`  
- Setup/Foundational/Polish **无** Story 标签  
- 描述均含精确仓库路径  
