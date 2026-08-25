# Implementation Plan：流式聊天代理

**Branch**: `015-stream-chat-proxy` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

stream=true 时 SSE 转发 SF07 事件；零事件失败用 JSON 错误；已开始流不混入错误 JSON。 落点 `services/proxy-gateway/internal/httpserver/proxy.go`。

## Technical Context

**Language/Version**: Go 1.25.12 / Python 3.11.15（按落点）
**Storage**: PostgreSQL 仅 API 持久实体；网关适配无库。
**Testing**: pytest / go test，先测后实现。
**Contracts**: 本目录 `contracts/` 与 `shared/contracts/` 按需提升。

## Constitution Check

Pre/Post: PASS — 无新微服务；秘密不落明文；整数 usage；TDD。

## Project Structure

```
services/proxy-gateway/internal/httpserver/proxy.go
```

## Complexity Tracking

无豁免。

## Phase 0/1 Summary

research 以源 SF15 + 宪章为准。实现优先领域端口与单测。
