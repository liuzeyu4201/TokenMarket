# Implementation Plan：代理 Key 认证

**Branch**: `011-proxy-key-auth` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

网关 Bearer 认证代理 Key，pepper HMAC 查找，失败 401 且不调上游。 落点 `services/proxy-gateway/internal/domain/proxyauth/`。

## Technical Context

**Language/Version**: Go 1.25.12 / Python 3.11.15（按落点）
**Storage**: PostgreSQL 仅 API 持久实体；网关适配无库。
**Testing**: pytest / go test，先测后实现。
**Contracts**: 本目录 `contracts/` 与 `shared/contracts/` 按需提升。

## Constitution Check

Pre/Post: PASS — 无新微服务；秘密不落明文；整数 usage；TDD。

## Project Structure

```
services/proxy-gateway/internal/domain/proxyauth/
```

## Complexity Tracking

无豁免。

## Phase 0/1 Summary

research 以源 SF11 + 宪章为准。实现优先领域端口与单测。
