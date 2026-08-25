# 请求字段允许列表：volcano-openai-compat v1

**Contract ID**: `volcano-openai-compat/request-field-allowlist/v1`  
**Owner**: proxy-gateway

出站 Chat Completions JSON **仅**可包含本表字段。未列出的顶层键 →
`unsupported_parameter`，不出站。

## 顶层字段

| 字段 | 必填 | 类型 | 约束 | 出站 |
|------|------|------|------|------|
| `model` | 是 | string | 非空；须为 V0.1 公开 allowlist 成员 | 映射后的上游 ID |
| `messages` | 是 | array | 1–128 项 | 是 |
| `stream` | 否 | boolean | | 是（若出现） |
| `temperature` | 否 | number | [0, 2] | 是（若出现） |
| `max_tokens` | 否 | integer | ≥ 1 | 是（若出现） |
| `top_p` | 否 | number | (0, 1] | 是（若出现） |
| `stop` | 否 | string 或 string[] | 数组长度 1–4；元素非空 | 是（若出现） |
| `presence_penalty` | 否 | number | [-2, 2] | 是（若出现） |
| `frequency_penalty` | 否 | number | [-2, 2] | 是（若出现） |
| `n` | 否 | integer | 必须 = 1 | 可省略；出现则写 `1` |

越界或不符类型 → `unsupported_parameter`（**不**静默钳制）。

## 明确拒绝（示例，非穷尽）

`tools`、`tool_choice`、`response_format`、`stream_options`、`user`、`seed`、
`logprobs`、`top_logprobs`、`logit_bias`、`thinking`、`extra_body`、
`functions`、`function_call`。

## messages[] 项

| 字段 | 必填 | 约束 |
|------|------|------|
| `role` | 是 | `system` \| `user` \| `assistant` |
| `content` | 是 | **任意 JSON 值原样转发**（string / parts / 多模态） |

其它键（`name`、`tool_calls`、`function_call` 等）→ `unsupported_parameter`。

未知 `role` 或空数组 → `unsupported_parameter`。

## 模型

- 公开 ID ∈ SF06 V0.1 Chat allowlist（配置 `VOLCANO_V01_CHAT_MODELS`）。
- 默认 `upstream = public`。
- `VOLCANO_CHAT_MODEL_MAP`：`public=upstream` 逗号分隔覆盖。
- 未知公开 ID → `unsupported_parameter`，不得改写为其它模型。
- 响应/事件中的 `model` 回写公开 ID。

## 体积

- 原始请求 JSON ≤ `VOLCANO_CHAT_MAX_BODY_BYTES`（默认 2097152）。
