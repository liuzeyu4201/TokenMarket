# Implementation Plan：非流式聊天代理

**Branch**: `012-nonstream-chat-proxy` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

公开 POST /v1/proxy/volcano/chat/completions 非流式：认证→选 Key→SF07 Complete→OpenAI JSON。 落点 `services/proxy-gateway/internal/httpserver/proxy.go`。

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

research 以源 SF12 + 宪章为准。实现优先领域端口与单测。
