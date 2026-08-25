# Data Model：火山方舟请求与响应兼容

**Feature**: `007-volcano-openai-compat`  
**Owner**: Proxy Gateway（`services/proxy-gateway/`）  
**System of record**: **无** — 本功能不持久化任何实体  
**Ephemeral**: 单次调用内存中的请求、出站表示、兼容结果与流事件

## 设计原则

- 卖家提供商 Key 仅出站期间驻留内存；买家代理 Key 不得进入本模型。
- 消息正文为敏感数据：本功能不持久化、默认不记日志。
- 结果与流事件为值对象；SF12/SF15 负责传输，SF17 负责用量落账。
- Token 计数为非负整数；未知不得写成 0。
- 时间：`created` 为 Unix 秒（兼容 Chat Completions）；遥测耗时用毫秒整数。

## Entity 1：Compatible Chat Request（瞬时）

调用方（未来 SF12/SF15 或测试）传入。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `platform` | string | yes | V0.1 仅 `volcano`；其它 → `unsupported_platform` |
| `api_key` | string | yes | 卖家方舟 Key；仅内存 |
| `request_id` | string | yes | 关联遥测 |
| `endpoint` | string | no | 缺省 `chat.completions`；其它 → `unsupported_endpoint` |
| `model` | string | yes | 公开模型 ID |
| `messages` | Message[] | yes | 至少 1 条 |
| `stream` | bool | no | 默认 false |
| `temperature` | number | no | [0, 2] |
| `max_tokens` | int | no | ≥ 1 |
| `top_p` | number | no | (0, 1] |
| `stop` | string or string[] | no | 数组 ≤ 4 |
| `presence_penalty` | number | no | [-2, 2] |
| `frequency_penalty` | number | no | [-2, 2] |
| `n` | int | no | 若出现必须为 1 |
| `deadline` | duration | no | 缺省由适配层套 60s |

### Message

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `role` | enum | yes | `system` \| `user` \| `assistant` |
| `content` | JSON value | yes | **原样转发**；本层不解释形态 |

消息对象允许出现的键仅为 `role`、`content`。其它消息级键（如 `name`、`tool_calls`）→ `unsupported_parameter`，与顶层 `tools` 拒绝一致。content **内部**形态不在此限。

**Invariants**:

- 禁止未声明**顶层**键进入出站 JSON。
- `api_key` 去空白后非空。
- 原始请求 JSON 体积 ≤ `max_body_bytes`（默认 2 MiB）。
- `messages` 条数 ≤ 128。

**Lifecycle**: 调用开始构造 → 过滤映射后出站 → 返回前丢弃 Key 引用。

## Entity 2：Provider Chat Request（瞬时）

火山方舟 JSON 体：允许列表字段 + 映射后的 `model` + 原样 `messages[].content`。
头见 [header-allowlist.md](./contracts/header-allowlist.md)。

## Entity 3：Compatible Chat Result（非流式值对象）

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `error_category` | enum | yes | 见分类表 |
| `id` | string | when success | 上游 id；缺失成功形状则不进入 success |
| `object` | string | when success | 固定 `chat.completion` |
| `created` | int | when success | Unix 秒 |
| `model` | string | when success | **公开**模型 ID |
| `choices` | Choice[] | when success | 至少 1 个；缺失 → 不得标 success |
| `usage` | Usage | no | 见 Entity 5；不完整时 omit 或带 status |
| `usage_status` | enum | yes | `complete` \| `missing` \| `inconsistent` \| `not_applicable` |
| `finish_reason` | string | when success | 来自 `choices[0]` 或契约字段 |
| `retry_after_seconds` | int | when rate_limited | ≥ 1 |
| `suggested_action` | enum | optional | `fix_parameter` \| `fix_credential` \| `retry_later` \| `unsupported` |
| `credential_ref` | string | optional | 仅遥测 |

`not_applicable`：参数错误、认证失败等未曾生成。

### Choice（成功时）

| Field | Type | Required |
|-------|------|----------|
| `index` | int | yes |
| `message.role` | string | yes |
| `message.content` | JSON value | 按上游；本层不改写 |
| `finish_reason` | string | 可空字符串按上游 |

**Invariants**:

- `error_category=success` ⇒ `choices` 非空。
- `usage_status=missing` ⇒ 不得出现全 0 的官方 usage 对象。
- 结果 JSON 不含 `api_key`。

## Entity 4：Compatible Stream Event（瞬时）

按顺序 yield 给调用方。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `kind` | enum | yes | `delta` \| `done` \| `truncated` \| `error` |
| `id` | string | when delta | |
| `object` | string | when delta | `chat.completion.chunk` |
| `created` | int | when delta | |
| `model` | string | when delta | 公开 ID |
| `choices` | chunk choices | when delta | `delta`/`finish_reason`/`index` |
| `usage` | Usage | optional | 常在末块 |
| `error_category` | enum | when error or truncated | truncated → `truncated_stream` |
| `retry_after_seconds` | int | when rate_limited 且 kind=error | |

**State machine（单次流）**:

```text
start
  ├─ 零 yield 前失败 ──► kind=error（结构化类别）──► end
  ├─ yield delta* ──┬─ 正常 [DONE] ──► kind=done（至多一次）──► end
  │                 └─ 失败/EOF/取消 ──► kind=truncated ──► end
  └─ （禁止：error JSON 混在 delta 之后）
```

不变量：`done` 与 `truncated` 互斥；`done` 至多一次；`truncated` 不得再补 `done`。

## Entity 5：Usage Observation（值对象）

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `prompt_tokens` | int or omit | 完整时 yes | ≥ 0 |
| `completion_tokens` | int or omit | 完整时 yes | ≥ 0 |
| `total_tokens` | int or omit | 完整时 yes | ≥ prompt+completion |
| `status` | enum | yes | `complete` \| `missing` \| `inconsistent` |
| `source` | enum | yes | `upstream`（本功能只此值；估算属 SF17） |

不变量见 [usage-observation.md](./contracts/usage-observation.md)。本功能不落账。

## Entity 6：Adapter Error Classification（逻辑枚举）

非存储。枚举与映射见 [error-classification.md](./contracts/error-classification.md)。

永久类仅 `invalid` / `forbidden`。`truncated_stream`、`timeout`、`rate_limited`、
`temporary_unavailable`、`invalid_response`、`unsupported_*` 不得被本功能写成
持久凭证 invalid（调用方契约，同 SF06 纪律）。

## 关系

```text
Compatible Chat Request
    └─(filter+map)→ Provider Chat Request
                         ├─ non-stream → Compatible Chat Result
                         │                 └─ Usage Observation
                         └─ stream → Compatible Stream Event*
                                           └─ optional Usage on last delta/done
```
