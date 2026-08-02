# 任务：火山方舟凭证与额度验证

**输入**: 设计文档来自 `/specs/006-volcano-key-validation/`

**前置**: `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`

**语言**: 任务描述与备注默认简体中文；标识符、路径、API 字段、环境变量、枚举保持原文。

**测试**: 每次行为变更均 **必须** 先写测试并在实现前观察到失败。`services/proxy-gateway/internal/domain/providervalid/` 与 volcano 适配相关包要求 ≥80% 行覆盖率；错误分类、脱敏、`quota_unavailable` 禁止假 0、并发闸门、取消/超时分支须直接断言。

**组织**: 按用户故事分组。Setup + Foundational 阻塞全部故事。

| 故事 | 优先级 | MVP? | 内容 |
|------|--------|------|------|
| US1 | P1 | **是** | 验证流水线：models 探活 + allowlist + 默认 `quota_unavailable` + 可注入额度成功/零额 + 内部 HTTP |
| US2 | P1 | 建议同批 | 稳定失败分类（invalid/forbidden/rate_limited/timeout/…）与 `retry_after_seconds` |
| US3 | P2 | 其后 | 3s 截止、取消传播、并发闸门 32/1、有界重试 |

**MVP 范围**: Phase 1–3（US1）。可交付内部验证建议 **US1+US2+US3**。

**明确不在任务内**: Key 持久化/加密（SF08）、健康调度（SF16）、代理转发、多平台、真实火山默认 CI、官方余额扣减。

## 格式：`[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件，同批次无未完成依赖）
- **[Story]**: `[US1]` / `[US2]` / `[US3]` 仅用于故事阶段
- 每个任务须包含精确文件路径

## 路径约定

- Gateway: `services/proxy-gateway/`
- 特性契约源: `specs/006-volcano-key-validation/contracts/`
- 共享契约（实现时）: `shared/contracts/volcano-key-validation/v1/`
- 领域: `services/proxy-gateway/internal/domain/providervalid/`
- 应用: `services/proxy-gateway/internal/application/`
- 适配: `services/proxy-gateway/internal/infrastructure/platform/volcano/`
- 闸门: `services/proxy-gateway/internal/concurrency/`
- HTTP: `services/proxy-gateway/internal/httpserver/`
- 测试: 与包同目录 `*_test.go`（Go 惯例）

---

## Phase 1: Setup（共享基础设施）

**目的**: 提升契约、包骨架、配置占位；尚无验证业务行为。

- [x] T001 将特性契约提升至 `shared/contracts/volcano-key-validation/v1/`：复制 `specs/006-volcano-key-validation/contracts/` 下 OpenAPI 与 markdown（`volcano-key-validation.openapi.yaml`、`error-classification.md`、`consumer-merge-rules.md`、`upstream-volcano-models.md`、`v01-chat-models.md`），并在 `shared/contracts/README.md`（或等价索引）登记所有权/版本
- [x] T002 [P] 在 `services/proxy-gateway/README.md` 增加 volcano-key-validation v1 契约索引与内部路由说明链接
- [x] T003 [P] 创建包骨架（可编译空文件/包注释）：`services/proxy-gateway/internal/domain/providervalid/`、`services/proxy-gateway/internal/application/`、`services/proxy-gateway/internal/infrastructure/platform/volcano/`、`services/proxy-gateway/internal/concurrency/`、`services/proxy-gateway/internal/infrastructure/platform/volcano/fixtures/`
- [x] T004 [P] 在 `services/proxy-gateway/internal/domain/providervalid/contract_assets_test.go`（或 `shared/` 等价测试）添加契约资产存在/OpenAPI YAML 可解析冒烟测试
- [x] T005 [P] 在仓库根 `.env.example` 文档化占位（无真实密钥）：`PROVIDER_VALIDATE_INTERNAL_ENABLED`（默认 false）、`PROVIDER_VALIDATE_INTERNAL_TOKEN`、`PROVIDER_VALIDATE_BIND`（默认 `127.0.0.1`）、`PROVIDER_VALIDATE_ALLOW_NON_LOOPBACK`（默认 false）、`VOLCANO_VALIDATE_BASE_URL`、`VOLCANO_V01_CHAT_MODELS`、`VOLCANO_VALIDATE_GLOBAL_CONCURRENCY`、`VOLCANO_VALIDATE_PER_CREDENTIAL_CONCURRENCY`、`VOLCANO_VALIDATE_DEFAULT_RETRY_AFTER_SECONDS`、`VOLCANO_VALIDATE_MAX_RETRY_AFTER_SECONDS`、`VOLCANO_VALIDATE_GATE_HMAC_SECRET`；注释标明非 local 不得仅靠静态 token 对公网暴露

**检查点**: 契约可发现；空包存在；无验证业务行为。

---

## Phase 2: Foundational（阻塞性前置）

**目的**: 领域类型、枚举、分类表、脱敏、配置加载、测试工厂；阻塞全部用户故事。

**关键**: 本阶段完成前不得开始 US1–US3 业务实现。先写 foundational 测试并观察到失败。

- [x] T006 [P] 在 `services/proxy-gateway/internal/domain/providervalid/types_test.go` 添加失败测试：`CredentialValidationRequest`/`CredentialValidationResult` 必填字段与 `error_category` 枚举全集对齐 `shared/contracts/volcano-key-validation/v1/error-classification.md`
- [x] T007 [P] 在 `services/proxy-gateway/internal/domain/providervalid/classify_test.go` 添加失败测试：HTTP status → `error_category` 默认表（401→invalid、403→forbidden、429→rate_limited、5xx→temporary_unavailable、超时→timeout）
- [x] T008 [P] 在 `services/proxy-gateway/internal/domain/providervalid/redaction_test.go` 添加失败测试：日志/错误字符串中不得出现完整 api_key；`credential_ref` 不可逆且同 Key 稳定
- [x] T009 [P] 在 `services/proxy-gateway/internal/domain/providervalid/result_invariants_test.go` 添加失败测试：`quota_unavailable` 时 `remaining_quota` 必须为空/null 且不得为 `"0"`；`rate_limited` 必须含 `retry_after_seconds≥1`
- [x] T010 在 `services/proxy-gateway/internal/domain/providervalid/types.go` 实现请求/结果类型与枚举（`validity`/`availability`/`error_category`/`suggested_action`），直至 T006 通过
- [x] T011 在 `services/proxy-gateway/internal/domain/providervalid/classify.go` 实现 status/网络错误 → 分类映射（尚不含完整编排），直至 T007 通过
- [x] T012 在 `services/proxy-gateway/internal/domain/providervalid/redaction.go` 实现脱敏与 `credential_ref`（HMAC/salted hash，密钥来自配置接口），直至 T008 通过
- [x] T013 在 `services/proxy-gateway/internal/domain/providervalid/invariants.go` 实现结果构造助手（强制 null 额度 / retry_after 规则），直至 T009 通过
- [x] T014 在 `services/proxy-gateway/internal/domain/providervalid/config.go`（或 `services/proxy-gateway/internal/httpserver` 可读的 config 包）定义验证配置结构体：base URL、allowlist、并发、retry 默认/钳制、internal token、enabled flag、`PROVIDER_VALIDATE_BIND`、`PROVIDER_VALIDATE_ALLOW_NON_LOOPBACK`；从环境加载；空 allowlist 失败；**非 local 且 enabled 且非回环/未允许非回环 → ValidateConfig 失败（C1 fail-closed）**
- [x] T015 [P] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/fixtures/` 添加合成金标 JSON（成功 models 列表、空 data、畸形 body）；**禁止**真实 Key
- [x] T016 [P] 在 `services/proxy-gateway/internal/observability/`（扩展既有包）增加验证指标钩子桩：`provider_validate_total`、`provider_validate_duration_seconds`、闸门拒绝计数（低基数标签：platform/error_category）

**检查点**: 类型/分类/脱敏/配置可单测；fixture 金标就位。

---

## Phase 3: User Story 1 - 验证有效凭证和额度 (Priority: P1) 🎯 MVP

**目标**: 内部调用可完成 models 探活、V0.1 模型交集、默认 `quota_unavailable`；通过可注入 `QuotaReader` 覆盖 `success`/`zero_quota`；提供领域 `Validate` 与内部 HTTP。

**独立测试**: mock 上游 200 + models；默认 Noop 额度 → `quota_unavailable` 且额度非 0；注入正额度+交集非空 → `success`；注入零额度 → `zero_quota`；交集空 → `no_supported_models`（在额度满足时）。

### User Story 1 的测试（先写并观察到失败）

- [x] T017 [P] [US1] 在 `services/proxy-gateway/internal/domain/providervalid/allowlist_test.go` 添加单元测试：交集、空交集、配置覆盖默认列表
- [x] T018 [P] [US1] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/client_test.go` 添加测试：httptest 模拟 GET `/models` 200 解析 `id` 列表；401/403 映射；畸形 JSON → 可识别协议错误
- [x] T019 [P] [US1] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/quota_test.go` 添加测试：`NoopQuotaReader` 恒定不可用；`StubQuotaReader` 正额/零额/错误
- [x] T020 [P] [US1] 在 `services/proxy-gateway/internal/application/validate_credential_test.go` 添加编排测试：默认 Noop → `quota_unavailable` 且 `remaining_quota` 空；Stub 正额+allowlist 命中 → `success`；Stub 零额 → `zero_quota`；正额+无交集 → `no_supported_models`
- [x] T021 [P] [US1] 在 `services/proxy-gateway/internal/httpserver/internal_validate_test.go` 添加 HTTP 测试：enabled+正确 token → 200 body 含 `error_category`；错误 token → 401；disabled → 404；响应 JSON 不含 api_key；**`platform=openai`（或非 volcano）→ HTTP 200 且 body `error_category=unsupported_platform`（非 422）**（I1）
- [x] T021a [P] [US1] 在 `services/proxy-gateway/internal/domain/providervalid/config_test.go`（或 httpserver 配置测试）添加 C1 负向：`APP_ENV=prod`（或 test）+ enabled + bind 非回环且 `ALLOW_NON_LOOPBACK=false` → 配置/启动校验失败；local + 回环 → 通过
- [x] T022 [P] [US1] 在 `services/proxy-gateway/internal/application/validate_credential_test.go`（或独立文件）添加：`platform!=volcano` → `unsupported_platform`（领域层，与 T021 HTTP 一致）
- [x] T023 [P] [US1] 在 `services/proxy-gateway/internal/domain/providervalid/consumer_merge_doc_test.go` 添加文档/契约一致性测试：`shared/contracts/volcano-key-validation/v1/consumer-merge-rules.md` 存在且声明临时类不得写永久 invalid（轻量字符串/结构断言即可）

### User Story 1 的实现

- [x] T024 [P] [US1] 在 `services/proxy-gateway/internal/domain/providervalid/allowlist.go` 实现 allowlist 加载与 `IntersectModels`，直至 T017 通过
- [x] T025 [US1] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/client.go` 实现 `ModelsClient`（GET models、context 取消、Bearer 头、解析 fixtures 形状），直至 T018 通过
- [x] T026 [US1] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/quota.go` 实现 `QuotaReader` 接口、`NoopQuotaReader`、测试用 `StubQuotaReader`，直至 T019 通过
- [x] T027 [US1] 在 `services/proxy-gateway/internal/application/validate_credential.go` 实现 `ValidateCredential` 编排（platform 检查 → models → quota → allowlist → 结果/`checked_at`/`suggested_action`），默认注入 Noop 额度，直至 T020/T022 通过
- [x] T028 [US1] 在 `services/proxy-gateway/internal/httpserver/internal_validate.go` 实现 `POST /internal/v1/provider-credentials/validate`：`platform` 为任意非空 string（**不要**用仅 volcano 的 schema 拒绝）；序列化对齐 OpenAPI；非 volcano 走领域结果 `unsupported_platform` 且 HTTP 200
- [x] T029 [US1] 在 `services/proxy-gateway/internal/httpserver/server.go`（及 `cmd/gateway/main.go` 若需）挂载内部路由；受 enabled + token + **C1 绑定/环境校验** 门禁；接线配置与 `ValidateCredential`；直至 T021/T021a 通过
- [x] T030 [US1] 重跑 US1 相关 `go test` 至绿；确认领域与 volcano 包覆盖率可统计

**检查点**: MVP — 内部验证可演示默认 `quota_unavailable` 与注入额度成功路径。

---

## Phase 4: User Story 2 - 获得稳定且安全的失败分类 (Priority: P1)

**目标**: 失败类型稳定映射，不依赖上游错误文案；`rate_limited` 始终带 `retry_after_seconds`（默认 5、钳制 300）；脱敏贯穿错误路径。

**独立测试**: 表驱动 401/403/429/5xx/畸形/限流无 Retry-After；日志扫描无完整 Key。

### User Story 2 的测试（先写并观察到失败）

- [x] T031 [P] [US2] 在 `services/proxy-gateway/internal/domain/providervalid/classify_table_test.go` 添加全量分类表驱动测试：对齐 `error-classification.md` 与 SC-001 类别列表（含 `invalid_response`）
- [x] T032 [P] [US2] 在 `services/proxy-gateway/internal/domain/providervalid/retry_after_test.go` 添加：`Retry-After` 秒/HTTP-date 解析；缺失→5；超过 max→钳制 300；`rate_limited` 字段必填
- [x] T033 [P] [US2] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/client_test.go` 扩展：429 带/不带 Retry-After；5xx；连接错误类别
- [x] T034 [P] [US2] 在 `services/proxy-gateway/internal/application/validate_credential_test.go` 扩展：各失败类别不返回完整 Key；`suggested_action` 映射合理（fix_credential/add_quota/retry_later/enable_models）
- [x] T035 [P] [US2] 在 `services/proxy-gateway/internal/domain/providervalid/redaction_leak_test.go` 添加：模拟含 Key 的上游 body/错误包装后，对外 error 与日志字段无明文 Key（SC-005）

### User Story 2 的实现

- [x] T036 [US2] 扩展 `services/proxy-gateway/internal/domain/providervalid/classify.go` 与 `retry_after.go` 完成表驱动与 retry 策略，直至 T031–T032 通过
- [x] T037 [US2] 扩展 `services/proxy-gateway/internal/infrastructure/platform/volcano/client.go` 错误路径分类与 Retry-After 提取，直至 T033 通过
- [x] T038 [US2] 扩展 `services/proxy-gateway/internal/application/validate_credential.go` 统一失败结果构造（validity/availability/suggested_action），确保临时类不声称零额或 invalid 认证，直至 T034 通过
- [x] T039 [US2] 在 `services/proxy-gateway/internal/domain/providervalid/redaction.go` 与 client 出站路径强化脱敏（Authorization 头、body 扫描），直至 T035 通过
- [x] T040 [US2] 重跑 US2 测试至绿；核对 SC-001/SC-001a 断言齐全

**检查点**: 失败分类可独立验收；无 Key 泄漏。

---

## Phase 5: User Story 3 - 取消与超时下的安全收尾 (Priority: P2)

**目标**: 3s 硬截止、取消传播、全局 32/单凭证 1 闸门、瞬时网络有界重试（总时长不破 3s）。

**独立测试**: 取消后迅速结束；强制超时 → `timeout`/`temporary_unavailable`；第 33 全局并发与同 Key 第 2 路不增加上游调用（SC-002a）。

### User Story 3 的测试（先写并观察到失败）

- [x] T041 [P] [US3] 在 `services/proxy-gateway/internal/concurrency/validate_gate_test.go` 添加：默认全局 32 第 33 拒绝；同 credential_ref 第 2 路拒绝；拒绝时不调用下游（用计数桩）
- [x] T042 [P] [US3] 在 `services/proxy-gateway/internal/application/validate_credential_timeout_test.go` 添加：context 100ms 取消；mock 上游阻塞时 ≤3s 返回 timeout/temporary 类
- [x] T043 [P] [US3] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/client_retry_test.go` 添加：瞬时网络错误至多 1 次重试且总时长 ≤ deadline；4xx/429 不重试
- [x] T044 [P] [US3] 在 `services/proxy-gateway/internal/concurrency/validate_gate_test.go` 添加：闸门拒绝返回 `temporary_unavailable`（或约定类别）且可重试语义
- [x] T045 [P] [US3] 在 `services/proxy-gateway/internal/application/validate_credential_test.go` 添加：取消路径后结果/日志无完整 Key（SC-006 可测子集）

### User Story 3 的实现

- [x] T046 [US3] 在 `services/proxy-gateway/internal/concurrency/validate_gate.go` 实现全局与单凭证信号量（默认 32/1，可配置；gate key 用不可逆哈希），直至 T041/T044 通过
- [x] T047 [US3] 将闸门接入 `services/proxy-gateway/internal/application/validate_credential.go`（先 Acquire 再上游；失败不调用 client）
- [x] T048 [US3] 在 `services/proxy-gateway/internal/application/validate_credential.go` 强制 `context` 截止 min(调用方, 3s)；传播取消，直至 T042 通过
- [x] T049 [US3] 在 `services/proxy-gateway/internal/infrastructure/platform/volcano/client.go` 实现有界重试策略，直至 T043 通过
- [x] T050 [US3] 重跑 US3 与全量 gateway 相关测试至绿；`-race` 跑闸门与编排测试

**检查点**: 取消/超时/并发可独立验收。

---

## Phase 6: Polish & Cross-Cutting Concerns

**目的**: 可观测性闭环、契约对齐、quickstart、覆盖率与安全扫描。

- [x] T051 [P] 在 `services/proxy-gateway/internal/application/validate_credential.go` 与 `services/proxy-gateway/internal/observability/` 接线真实指标与结构化日志字段（platform、error_category、duration、request_id、credential_ref；无 Key）
- [x] T052 [P] 在 `ops/runbooks/` 新增或扩展短 runbook：`ops/runbooks/volcano-key-validation.md`（invalid_response 告警、内部路由误开/公网暴露风险、额度始终 unavailable 分诊；明确 test/prod 启用前置：私网/回环/mTLS，禁止仅静态 token 对公网）
- [x] T053 按 `specs/006-volcano-key-validation/quickstart.md` 跑通替身验收并记录命令结果摘要到 `specs/006-volcano-key-validation/evidence/`（或 PR 描述）
- [x] T054 复核 `shared/contracts/volcano-key-validation/v1/upstream-volcano-models.md`：用当期官方文档更新复核记录表；确认默认仍为 Noop 额度或文档化新额度端点
- [x] T055 运行 `cd services/proxy-gateway && go test ./... -count=1` 与覆盖率：确认 `internal/domain/providervalid` 与 `internal/infrastructure/platform/volcano` ≥80% 行；分类与脱敏分支直接覆盖
- [x] T056 [P] 运行仓库 `make lint` / `make test`（或 gateway 目标）与 `make security-check`（若可用）：确认无真实 Key 入仓、夹具仅合成
- [x] T057 [P] 更新 `services/proxy-gateway/README.md`：如何启用内部验证、环境变量、**禁止** GetBalance 返回 0 的说明
- [x] T058 对照 `specs/006-volcano-key-validation/contracts/volcano-key-validation.openapi.yaml` 做实现字段最终对齐检查（handler 与 Result JSON）

**检查点**: 可合并；quickstart 可复现；契约与实现一致。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: 无依赖，立即开始
- **Phase 2 Foundational**: 依赖 Phase 1；**阻塞**全部用户故事
- **Phase 3 US1**: 依赖 Phase 2 → MVP
- **Phase 4 US2**: 依赖 Phase 2；可与 US1 并行（若人力足够），但通常接在 US1 编排之后以复用 `ValidateCredential`
- **Phase 5 US3**: 依赖 US1 编排骨架（T027）；可与 US2 部分并行（闸门文件独立）
- **Phase 6 Polish**: 依赖目标故事完成

### User Story Dependencies

- **US1 (P1)**: Foundational 后即可；无其他故事依赖
- **US2 (P1)**: 依赖分类/编排挂钩；逻辑上可独立测分类器，端到端需 US1 client
- **US3 (P2)**: 依赖 `ValidateCredential` 与 client 存在

### Within Each Story

1. 测试先写并失败  
2. 实现至测试绿  
3. 故事检查点再进入下一优先级  

### Parallel Opportunities

- Phase 1：T002–T005 可并行  
- Phase 2：T006–T009、T015–T016 可并行  
- US1 测试：T017–T023 可并行  
- US2 测试：T031–T035 可并行  
- US3 测试：T041–T045 可并行  
- Polish：T051/T052/T057 可并行  

---

## Parallel Example: User Story 1

```bash
# 并行启动 US1 测试（不同文件）：
Task: T017 allowlist_test.go
Task: T018 client_test.go
Task: T019 quota_test.go
Task: T021 internal_validate_test.go

# 实现顺序（有依赖）：
T024 allowlist → T025 client → T026 quota → T027 ValidateCredential → T028/T029 HTTP
```

## Parallel Example: User Story 3

```bash
Task: T041 validate_gate_test.go
Task: T042 validate_credential_timeout_test.go
Task: T043 client_retry_test.go
```

---

## Implementation Strategy

### MVP First（仅 US1）

1. Phase 1 Setup  
2. Phase 2 Foundational  
3. Phase 3 US1  
4. **STOP**：用 mock 演示默认 `quota_unavailable` + 注入 `success`  
5. 再合入 US2/US3  

### Incremental Delivery

1. Setup + Foundational → 基础就绪  
2. US1 → 内部验证 MVP  
3. US2 → 生产级分类与防泄漏  
4. US3 → 截止/取消/闸门  
5. Polish → 可合并证据  

### Parallel Team Strategy

1. 全员完成 Setup + Foundational  
2. Dev A：US1 编排 + HTTP  
3. Dev B：US2 分类/脱敏（与 A 协调 `classify.go`）  
4. Dev C：US3 闸门/超时（`concurrency/` 独立文件）  

---

## Notes

- [P] = 不同文件且无未完成依赖  
- 默认 **NoopQuotaReader**；禁止实现「无余额返回 0」  
- SF08/SF16 合并规则只交付契约与文档测试，不在本任务实现持久合并  
- 真实火山仅可选人工 smoke，不进默认 CI  
- 每完成一逻辑组建议 Conventional Commit（如 `feat(gateway): add volcano models client`）  
- 下一命令：`/speckit-implement` 或按 Phase 执行  

## Format Validation

- 全部任务以 `- [ ]` 开头  
- 全部含 Task ID（T001–T058）  
- 故事阶段任务均含 `[US1]`/`[US2]`/`[US3]`  
- Setup/Foundational/Polish **无** Story 标签  
- 描述均含精确仓库路径  

---

## Phase 7: Convergence

**目的**: 收口实现与 spec/plan/宪章之间的残余缺口（`/speckit-converge` 2026-08-01）。  
**前置**: Phase 1–6 已完成；本阶段仅追加未满足项，不改编号既有任务。

- [x] T059 在 `services/proxy-gateway/internal/concurrency/validate_gate_test.go` 与/或 `services/proxy-gateway/internal/application/validate_credential_test.go` 增加验收：`GlobalConcurrency=32` 时第 33 路 `Acquire`/`ValidateCredential` 失败且 models 调用次数不增加；`PerCredConcurrency=1` 时同 Key 第 2 路同理 — per **SC-002a** / **FR-012a** (`partial`)
- [x] T060 CRITICAL：在 `services/proxy-gateway/cmd/gateway/main.go`（及必要的 `internal/httpserver`）落实 plan C1：内部验证启用时，内部路由不得仅靠静态 token 暴露在公网监听上 — 非 local 下将监听绑定到 `PROVIDER_VALIDATE_BIND`（回环），或为 `/internal/v1/provider-credentials/validate` 使用独立回环 listener；并在测试中断言隔离语义 — per **Constitution II** / **plan: Security C1** / **research D9** (`partial`)
- [x] T061 在 `services/proxy-gateway/internal/application/validate_credential.go`（或注入的 `*slog.Logger`）于每次验证结束写一条结构化日志：`request_id`、`platform`、`error_category`、`duration_ms`、`credential_ref`；**禁止** api_key/Authorization — per **ER-006** / **T051** (`partial`)
- [x] T062 修正 `services/proxy-gateway/internal/observability/validate_metrics.go` 与 `ValidateCredential` 接线：指标 `platform` 标签使用请求平台（或规范化后的值），不得对 `unsupported_platform` 等结果硬编码 `volcano` — per **ER-006** (`partial`)
