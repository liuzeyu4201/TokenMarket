# Implementation Plan：可用 Key 池与轮询选择

**Branch**: `013-key-pool-rotation` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

仅 administrative_state=active 且 health_state=healthy；排除自买自卖；轮询。 落点 `services/proxy-gateway/internal/domain/keypool/`。

## Technical Context

**Language/Version**: Go 1.25.12 / Python 3.11.15（按落点）
**Storage**: PostgreSQL 仅 API 持久实体；网关适配无库。
**Testing**: pytest / go test，先测后实现。
**Contracts**: 本目录 `contracts/` 与 `shared/contracts/` 按需提升。

## Constitution Check

Pre/Post: PASS — 无新微服务；秘密不落明文；整数 usage；TDD。

## Project Structure

```
services/proxy-gateway/internal/domain/keypool/
```

## Complexity Tracking

无豁免。

## Phase 0/1 Summary

research 以源 SF13 + 宪章为准。实现优先领域端口与单测。
