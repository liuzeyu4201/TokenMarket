# 头允许列表：volcano-openai-compat v1

**Contract ID**: `volcano-openai-compat/header-allowlist/v1`  
**Owner**: proxy-gateway

## 出站（本功能设置，不转发调用方头）

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer <seller_api_key>` |
| `Content-Type` | `application/json` |
| `Accept` | `application/json`（非流式）或 `text/event-stream`（流式） |

禁止设置或转发：买家 `Authorization`、`Cookie`、`X-Internal-Token`、`X-API-Key`、
`X-Forwarded-*`、`X-Real-IP`、上游调试头。

## 回传（领域结果）

不把上游 HTTP 头交给调用方。限流只通过结果字段 `retry_after_seconds`。

丢弃：`Set-Cookie`、`Server`、`X-Request-Id`（上游）、追踪头、任意未列出头。

调用方自己的 `request_id` 由领域字段/日志保留，不依赖上游回显。
