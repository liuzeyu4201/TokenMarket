# 传输政策：native-passthrough v1.1

- SSE：按块转发并 flush，不解析/改写 event 名；idle timeout；客户端取消传播。
- WebSocket：仅 `transport=websocket` 端点转发 Upgrade/Connection；其它端点仍剥离 hop-by-hop。
- multipart/binary：流式，限制 Content-Length 与读取上限；禁止明文临时文件。
- 共享模式不得使用 `stateful=true` 端点（沿用 `DEDICATED_PROJECT_REQUIRED`）。
