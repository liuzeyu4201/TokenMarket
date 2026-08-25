# Phase 0 Research：火山方舟请求与响应兼容

**Feature**: `007-volcano-openai-compat`  
**Date**: 2026-08-24  
**Status**: Complete — Technical Context 中的未知项均已决议

## Decision 1：能力归属 proxy-gateway，无新微服务、无公开 HTTP

**Decision**: SF07 由 `services/proxy-gateway/` 拥有。交付同进程领域端口
`ChatCompletions`（非流式）与 `ChatCompletionsStream`（流式），由后续 SF12/SF15
在网关进程内调用。V0.1 **不**挂载公开 `/v1/proxy/...` 路由，也 **不**默认提供
内部 HTTP（避免再复制一套 SF06 的 C1 监听隔离）。验收以契约测试 + `httptest`
上游替身为主。

不新建服务；不把协议解析放入 Python API Service；Billing / Admin / Frontend
本功能无变更。不修改 SF06 的 `volcano-key-validation/v1` 破坏性字段。

**Rationale**: 宪章 I 与 `2-Go代理网关开发规范.md` 将平台适配放在网关。SF12/SF15
同属 gateway，同进程调用最简单且无跨服务密钥传递。SF06 内部 HTTP 是因为 SF08
在 API Service；本功能无此约束。

**Alternatives considered**:

- 内部 HTTP 供独立 curl：可测但引入 token/绑定/双 listener，与 SF12 重复。
- 在 API Service 实现转换：与网关热路径双源漂移。
- 独立 compat-service：V0.1 不足以承担新服务/ADR。

## Decision 2：上游为方舟数据面 `POST /api/v3/chat/completions`（OpenAI 兼容）

**Decision**: 复用 SF06 数据面 Base URL（默认
`https://ark.cn-beijing.volces.com/api/v3`，可配置）与
`Authorization: Bearer <api_key>`：

```http
POST {base_url}/chat/completions
Content-Type: application/json
Authorization: Bearer <api_key>
```

官方文档（计划日复核）：

| 文档 | 结论 |
|------|------|
| 对话(Chat) API `82379/1494384` | `POST .../api/v3/chat/completions`；`messages.content` 为 string 或多模态数组 |
| 兼容 OpenAI SDK `82379/1330626` | Base URL 即 `/api/v3`；可用 OpenAI SDK `chat.completions.create` |
| SF06 `upstream-volcano-models.md` | 同一 Base URL + Bearer |

因此 **转换层是「允许列表过滤 + 模型映射 + SSE 边界解析 + 错误分类」**，不是
私有 RPC ↔ OpenAI 的全量重写。不得因此透传未声明顶层字段（澄清 Q1）。

方舟扩展字段（如 `thinking` / `extra_body`）**不**在 V0.1 允许列表，出现则
`unsupported_parameter`。

流式：`stream=true` 时 `Accept: text/event-stream`；事件为 SSE `data:` JSON 行，
正常结束为 `data: [DONE]`。

**Rationale**: 官方已兼容 OpenAI，保持薄适配可降低漂移，同时用允许列表锁住
V0.1 语义。

**Alternatives considered**:

- 管控面 IAM 签名调用：需要平台持有卖家 AK/SK，超出输入模型。
- 引入火山官方 Go SDK：额外依赖面；标准库 `net/http` 足够。

## Decision 3：请求顶层允许列表 = 扩展采样集（澄清 Q1）

**Decision**: 出站 JSON **只含**下列顶层键（出现才写入，不填官方默认值）：

| 字段 | 规则 |
|------|------|
| `model` | 必填；公开 ID → 映射后的上游 ID |
| `messages` | 必填；非空数组；`role` ∈ {`system`,`user`,`assistant`} |
| `stream` | 可选 bool |
| `temperature` | 可选；数值 ∈ [0, 2] |
| `max_tokens` | 可选；正整数 |
| `top_p` | 可选；数值 ∈ (0, 1] |
| `stop` | 可选；string 或 string[]（≤4，每项非空） |
| `presence_penalty` | 可选；数值 ∈ [-2, 2] |
| `frequency_penalty` | 可选；数值 ∈ [-2, 2] |
| `n` | 可省略；若出现必须为整数 `1` |

其它顶层键（含 `tools`、`tool_choice`、`response_format`、`stream_options`、
`user`、`seed`、`logprobs`、`thinking`）→ `unsupported_parameter`，**不出站**。

未知 `role`、空 `messages`、非法 JSON 类型、`n≠1` 同上。

`messages[].content` **不**在本决策校验（见 Decision 4）。

取值越界 → `unsupported_parameter`（不静默钳制，以免改变采样意图）。

**Rationale**: 澄清 Q1；比「仅四字段」更接近换 Key 即用，又不会把工具调用/
结构化输出拉进 V0.1。

**Alternatives considered**: 严格四字段；忽略未知键；原样转发未知键。均已在
clarify 否决。

## Decision 4：`messages[].content` 原样转发（澄清 Q2）

**Decision**: content 可以是 JSON string、text parts 数组或含 `image_url` 等
非 text 的多模态 parts。适配层 **不**校验、不扁平化、不丢弃部分。上游拒绝
某种形态时走 Decision 8 的错误分类。

顶层 `tools` / `response_format` 仍拒绝（Q1）；「多模态」仅当作为独立端点或
未声明顶层字段时拒绝。

**Rationale**: 澄清 Q2；官方 Chat API 本身接受 string 与多模态数组。

**Alternatives considered**: 仅 string；仅 text parts；静默拼接。已否决。

## Decision 5：usage 观察与成功对象解耦（澄清 Q3）

**Decision**:

- 标准化整数 `prompt_tokens` / `completion_tokens` / `total_tokens`（禁止二进制浮点）。
- 三分项均存在且 `total >= prompt + completion` → `usage_status=complete`。
- 缺失任一分项 → `usage_status=missing`（字段 omit/null，**不得**填 0）。
- 三分项存在但 `total < prompt + completion`，或出现负数 → `usage_status=inconsistent`
  （保留原始整数供诊断，**不得**改写后当官方值）。
- 只要非流式 `choices` 可读（或流式已正常结束），仍交付兼容成功对象 / `[DONE]`。
- 本层 **不估算** usage（SF17 的事）。
- 缺少 `choices`（非流式成功形状）→ `invalid_response`，与 usage 无关。

**Rationale**: 澄清 Q3；宪章 III 禁止用 0 表示未知计量。

**Alternatives considered**: usage 问题即整次 `invalid_response`；本层估算。已否决。

## Decision 6：有界截止默认 60 秒，生成不重试（澄清 Q4）

**Decision**:

```text
deadline = min(caller_deadline if set, VOLCANO_CHAT_MAX_DEADLINE_SECONDS)
if caller has no deadline:
  deadline = VOLCANO_CHAT_DEFAULT_DEADLINE_SECONDS  # 默认 60
```

默认：`DEFAULT=60`，`MAX=300`（钳制异常大截止，可配置）。到期 → `timeout`，
传播 `context` 取消。

**禁止**对生成请求自动重试（含 5xx）。仅出站前的参数错误不发请求。

取消：停止解析/出站；零事件 → 向调用方返回 `ctx.Err()`（不伪装成功，不记永久
invalid）；已出事件 → `truncated_stream` 且不补 `[DONE]`。

**Rationale**: 澄清 Q4；宪章 I/VI 有界超时；生成非幂等。

**Alternatives considered**: 无截止则无限等；强制调用方必须带截止。已否决。

## Decision 7：流式失败分界 = 是否已交出兼容事件（澄清 Q5）

**Decision**: 以适配层 **已经向调用方 yield 的兼容事件计数** 为准（不是上游
TCP 是否已有字节，也不是公开 HTTP 是否已写头——后者属 SF15）。

| 已交出兼容事件 | 上游失败/超时/EOF | 行为 |
|----------------|-------------------|------|
| 0 | 401/403/429/5xx/非法首包/截止 | 结构化错误，与非流式同类；不开空流；不发 `[DONE]` |
| ≥1 | 断开/截止/非法后续块 | `truncated_stream`；保留顺序；不补 `[DONE]`；不插错误 JSON |

正常结束：唯一 `[DONE]`，即使 usage 不完整。

**Rationale**: 澄清 Q5；对齐 SF15「流开始前用错误结构、开始后不能混入 JSON 错误体」。

**Alternatives considered**: 流式一律截断；已出事件仍写错误对象。已否决。

## Decision 8：错误分类（扩展 SF06 纪律，独立契约）

**Decision**: 新契约 `volcano-openai-compat/v1`，**不**把 chat 特有枚举塞进
SF06 v1（避免验证结果被截断流污染）。HTTP→类别复用 SF06 表：

| 上游信号 | `error_category` | 可重试 | 可标永久 invalid |
|----------|------------------|--------|------------------|
| 200 + 可读 choices（或流正常结束） | `success` | — | 否 |
| 出站前字段/role/`n`/未声明键 | `unsupported_parameter` | 否 | 否 |
| 非 Chat Completions 端点意图 | `unsupported_endpoint` | 否 | 否 |
| 公开模型不在映射/allowlist | `unsupported_parameter` | 否 | 否 |
| 401 | `invalid` | 否 | **是** |
| 403 | `forbidden` | 否 | **是** |
| 429 | `rate_limited` + `retry_after_seconds` | 是 | 否 |
| 截止 / 上游超时 | `timeout` | 是 | 否 |
| 5xx / 连接错误 | `temporary_unavailable` | 是 | 否 |
| 200 但无 choices / 损坏 JSON（零事件） | `invalid_response` | 否 | 否 |
| 已出事件后截断 | `truncated_stream` | 视调用方 | 否 |
| platform ≠ volcano | `unsupported_platform` | 否 | 否 |

`retry_after_seconds`：优先 `Retry-After`；缺失默认 5；钳制 300。与 SF06 同一
默认配置键可复用。

400 等其它 4xx：若 JSON 能识别为参数类则 `unsupported_parameter`，否则
`invalid_response`（不得用上游 `message` 原文做主分类）。

**Rationale**: ER-001；SF06 合并纪律（临时类不得写永久 invalid）继续适用。

## Decision 9：SSE 解析器（增量、不聚合完整响应）

**Decision**: 自研基于 `bufio` 的事件分帧：

- 以空行分隔事件；`:` 开头为注释；忽略未知 `event:`。
- 多行 `data:` 用 `
` 拼接后再 JSON 解析；完整事件前不向调用方 yield。
- 半个 UTF-8 / 半个 JSON：留在缓冲，不输出损坏片段。
- `data: [DONE]`（允许周围空白）→ 正常终止；只允许一次。
- 不把整个上游 body 拼成 `[]byte` 再切。
- 模糊测试：非法 UTF-8、超长行、随机分块；不得 panic。

**Rationale**: FR-005/SC-005；标准库足够，避免第三方 SSE 库语义漂移。

**Alternatives considered**: 第三方 SSE 库；先 `io.ReadAll` 再解析（违反流式 SLO）。

## Decision 10：出站/回传头允许列表

**Decision**:

出站 **只设**：

- `Authorization: Bearer <seller_api_key>`
- `Content-Type: application/json`
- `Accept: application/json` 或 `text/event-stream`（由 `stream` 决定）

**禁止**转发：买家 `Authorization`、`Cookie`、`X-Internal-Token`、`X-API-Key`、
任意 `X-Forwarded-*`、调试头。

回传给调用方：领域结果 **不**透传上游头。限流只通过 `retry_after_seconds`。
上游 `Set-Cookie`、追踪、Server 指纹丢弃。

**Rationale**: FR-009/010；宪章 II。

## Decision 11：模型映射默认恒等，可配置覆盖

**Decision**: 公开模型 ID 必须 ∈ V0.1 Chat allowlist（与 SF06
`VOLCANO_V01_CHAT_MODELS` / `v01-chat-models.md` 对齐）。默认
`upstream_id = public_id`。可选配置 `VOLCANO_CHAT_MODEL_MAP`
（`public=upstream` 逗号分隔）覆盖。响应与流事件的 `model` **回写公开 ID**。
未知公开模型 → `unsupported_parameter`，不得改成别的模型。

种子仍为占位 `doubao-pro-32k` 等；实现任务必须用当期官方 Model ID 更新复核表。

**Rationale**: FR-013；官方常用 Endpoint ID（`ep-...`）与展示名不同，需要可配置映射。

## Decision 12：请求体上限与安全默认

**Decision**: 序列化前原始 JSON 上限默认 **2 MiB**
（`VOLCANO_CHAT_MAX_BODY_BYTES`，可配置）。超限 → `unsupported_parameter`，
不出站。消息条数默认上限 128；超限同样参数错误。空 `messages` 拒绝。

不记录消息正文；日志仅 `request_id`、公开模型、`stream`、`error_category`、
耗时、`credential_ref`（复用 SF06 不可逆哈希）。

测试夹具仅合成内容与合成 Key。

**Rationale**: 边界「超大请求体」未定量；2 MiB 为可测默认。宪章 II。

## Decision 13：测试策略

**Decision**:

- 黄金 JSON：请求过滤、响应标准化、usage 三种状态、模型回写。
- SSE：拆包、合包、注释、`[DONE]`、截断、零事件失败 vs 已出事件失败。
- httptest：401/403/429/5xx/超时/取消；429 无 Retry-After → 5。
- 负向：未声明顶层键、`n=2`、`tools`、`response_format`、未知 role、content
  多模态 **不得**被拒绝。
- 模糊：JSON/SSE 解析器不得 panic（补充，不替代 SC-005 计数门禁）。
- `go test -race` 覆盖流解析与取消。
- `domain/chatcompat` 与 `platform/volcano` chat 路径 ≥80% 行覆盖。
- **SC-002 验收口径（分析 F1）**：
  - 目标仍为非流式转换 P95 < 5 ms、单事件 P95 < 1 ms（不含上游等待）。
  - **CI 红线**：禁止为转换 `ReadAll` 全部上游字节；正确性测试必须绿。
  - **合入证据**：`go test -bench` 输出 + OS/CPU/`GOMAXPROCS` 写入
    `specs/007-volcano-openai-compat/evidence/`。默认 CI 不对 5 ms/1 ms 墙钟 fail。
- **SC-005 验收口径（分析 F2）**：
  - **CI 红线**：确定性生成 ≥10_000 个 SSE 事件（拆包/合包/注释/`[DONE]`），
    零丢失、零重复、零补造终止；内存管道即可，禁止真实网络。
  - fuzz 不得用来「替代」该 10k 计数测试。
- 真实火山：可选人工 smoke，**不**进默认 CI。

**Rationale**: 宪章 V；与 SF06 证据风格一致。

## Decision 14：可观测性与运维

**Decision**:

指标（低基数）：`provider_chat_total{platform,stream,error_category}`、
`provider_chat_duration_seconds`、`provider_chat_truncated_total`。

日志：每次完成一条结构化记录；**无** messages / api_key / Authorization。

告警：`invalid_response` 与 `truncated_stream` 比率异常 → runbook 分诊（上游
契约变化 vs 网络截断）。

回滚：仅网关镜像；无迁移；无 flag 也可通过停用 SF12 路由（尚未交付）隔离。
本功能代码路径仅在 SF12/SF15 接线后进入生产流量。

**Rationale**: 宪章 VI。

## 官方文档复核清单（实现前必做）

- [ ] Chat Completions 路径仍为 `POST /api/v3/chat/completions`
- [ ] 鉴权仍为 Bearer API Key
- [ ] 流式仍为 SSE + `[DONE]`
- [ ] usage 字段名仍为 `prompt_tokens` / `completion_tokens` / `total_tokens`
- [ ] 无新的「必须透传」顶层字段改变 V0.1 允许列表（若有 → 契约小版本）
- [ ] 更新 `contracts/upstream-volcano-chat.md` 复核表

## 已解决的 NEEDS CLARIFICATION 映射

| 项 | 去向 |
|----|------|
| 请求字段策略 | 澄清 Q1 / D3 |
| content 形态 | 澄清 Q2 / D4 |
| usage 不完整 | 澄清 Q3 / D5 |
| 缺截止 | 澄清 Q4 / D6 |
| 流式失败分界 | 澄清 Q5 / D7 |
| 官方端点 | D2（计划日文档） |
| 是否内部 HTTP | D1：否 |
| 头允许列表 | D10 |
| 模型映射 | D11 |
| 生成重试 | D6：禁止 |
