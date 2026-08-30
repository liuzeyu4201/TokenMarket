# Header 政策：native-passthrough v1

**Owner**: Proxy Gateway  
**Version**: 1.0.0

平台只替换 upstream 鉴权与目标 Host。下列头不得转发到 upstream，也不得把 upstream 凭证头回传给买家。

## 入站剥离（不转发）

| Header | 原因 |
|--------|------|
| Connection, Keep-Alive, Proxy-*, TE, Trailer, Transfer-Encoding, Upgrade（非 WS 目录端点） | hop-by-hop |
| Cookie, Set-Cookie | 会话隔离 |
| Authorization（买家） | 由平台替换 |
| X-Internal-Token, X-API-Key | 内部凭证 |
| X-Forwarded-For, X-Forwarded-Host, X-Forwarded-Proto, X-Real-IP | 内部网络 |

## 入站可透传（示例，非穷尽）

Content-Type, Accept, Accept-Language, Idempotency-Key, OpenAI-Beta, anthropic-version, anthropic-beta, x-goog-api-client 以及目录协议要求的其它业务头。

## 出站到 upstream 的鉴权

| 协议 | 头 |
|------|-----|
| openai | `Authorization: Bearer <credential>` |
| anthropic | `x-api-key: <credential>` |
| vertex | `Authorization: Bearer <credential>` |

## 回传到客户端

原样复制安全允许的响应头（Content-Type, Retry-After, Cache-Control 等）。  
剥离：Set-Cookie、Authorization、x-api-key、X-Internal-Token。  
平台始终设置 `X-Request-ID`（本请求 ID，不采用上游值覆盖关联）。
