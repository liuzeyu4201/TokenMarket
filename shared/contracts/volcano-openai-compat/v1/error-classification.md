# 错误分类契约：volcano-openai-compat v1

**Contract ID**: `volcano-openai-compat/error-classification/v1`  
**Owner**: proxy-gateway  
**Consumers**: SF12 非流式代理、SF15 流式代理、SF16 健康（分类信号）、SF17 用量（不消费失败类）

独立于 `volcano-key-validation/v1`。HTTP 映射习惯对齐 SF06，但枚举集合为本功能所有。

## 稳定枚举

| error_category | 含义 | 调用方是否可标永久 invalid | suggested_action |
|----------------|------|---------------------------|------------------|
| `success` | 兼容成功对象或流正常结束 | 否 | — |
| `invalid` | 上游认证失败 | **是** | `fix_credential` |
| `forbidden` | 上游权限不足 | **是** | `fix_credential` |
| `rate_limited` | 上游限流 | 否 | `retry_later` |
| `temporary_unavailable` | 暂时故障/连接错误 | 否 | `retry_later` |
| `timeout` | 截止或上游超时 | 否 | `retry_later` |
| `invalid_response` | 成功形状不可读（零事件/无 choices） | 否 | 告警 |
| `unsupported_parameter` | 未声明字段、越界、`n≠1`、未知模型/role | 否 | `fix_parameter` |
| `unsupported_endpoint` | 非 Chat Completions | 否 | `unsupported` |
| `unsupported_platform` | 非 volcano | 否 | `unsupported` |
| `truncated_stream` | 已交出事件后截断 | 否 | `retry_later` |

`rate_limited` MUST 含 `retry_after_seconds`（秒，正整数）：优先上游 `Retry-After`，缺失默认 5，钳制 300。

## HTTP 上游 → 分类（零事件 / 非流式）

| 上游 HTTP | 默认 error_category |
|-----------|---------------------|
| 401 | `invalid` |
| 403 | `forbidden` |
| 429 | `rate_limited` |
| 408 / client deadline | `timeout` |
| 5xx | `temporary_unavailable` |
| 网络拨号/连接错误 | `temporary_unavailable` |
| 其它 4xx 且可识别为参数 | `unsupported_parameter` |
| 其它 4xx | `invalid_response` |
| 200 + 无可读 choices | `invalid_response` |
| 200 + choices 可读 | `success`（usage 另见 status） |

已交出 ≥1 兼容事件后的失败 **不得** 改走上表的结构化 success/invalid_response 混入流；一律 `truncated_stream`。

不得依赖上游 `message` 文案做主分类。

## 可重试

`rate_limited`、`timeout`、`temporary_unavailable`、`truncated_stream` → 调用方可重试（**本功能不代重试**）。  
`invalid`、`forbidden`、`unsupported_*`、`invalid_response` → 不得盲目重放同一生成。
