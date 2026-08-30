# 平台错误码：native-passthrough v1

透传内核在**未取得 upstream HTTP 响应**或**目录/协议判定失败**时使用统一信封 `code`。  
一旦 upstream 返回了状态码与正文，必须原样复制，不得改写成另一厂商错误 JSON。

| code | 何时 | HTTP |
|------|------|------|
| `PROTOCOL_UNRESOLVED` | 无法唯一确定 openai/anthropic/vertex | 400 |
| `ENDPOINT_NOT_CATALOGED` | method/path 无目录记录 | 404 |
| `CONTROL_PLANE_NOT_ALLOWED` | 控制面路径 | 403 |
| `PREVIEW_NOT_ENABLED` | preview/beta 未 opt-in | 403 |
| `DEDICATED_PROJECT_REQUIRED` | 有状态端点且非专享 | 403 |
| `REQUEST_TOO_LARGE` | 请求体超过上限 | 413 |
| `UPSTREAM_TIMEOUT` | 传输超时且无响应体 | 504 |
| `CLIENT_CANCELED` | 客户端取消 | 499 语义（HTTP 499 或 400 信封） |
| `NO_UPSTREAM` | Selector 无可用连接（SF23 前 fail-closed） | 503 |

平台信封字段：`code`, `message`, `data`, `request_id`, `timestamp`。  
不得把上述 code 写成 OpenAI `error.type` 或 Anthropic `type=error` 形状。
