# Phase 0 Research：原生透传内核

## Decision 1：独立 `passthrough` 包，不复用 chatcompat

**Decision**: Volcano OpenAI 兼容适配器继续服务 `/v1/proxy/volcano/chat/completions`。三厂商内核禁止 import chatcompat。

## Decision 2：httputil.ReverseProxy 作字节/流通路

**Decision**: 不解析业务 JSON。Director 只改 URL/Host/鉴权头。FlushInterval 支持 SSE。

## Decision 3：协议解析顺序

**Decision**: 路径前缀 → Host → 目录唯一命中 → anthropic-version / `/v1/projects/`。失败 `PROTOCOL_UNRESOLVED`。

## Decision 4：Selector 端口

**Decision**: `Select(ctx, protocol, endpointID) (Upstream, error)`。测试 StaticSelector；生产默认 FailClosed（`NO_UPSTREAM`）直到 SF23。

## Decision 5：错误分层

**Decision**: 未发出或传输失败 → 平台信封。已获得 upstream HTTP 响应 → 原样复制状态与正文。
