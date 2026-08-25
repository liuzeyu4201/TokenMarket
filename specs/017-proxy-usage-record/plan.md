# Implementation Plan：代理请求用量记录

**Branch**: `017-proxy-usage-record` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

持久化 SF07 Usage Observation；missing 禁止假 0。 落点 `services/api-service/app/domain/usage/`。

## Technical Context

**Language/Version**: Go 1.25.12 / Python 3.11.15（按落点）
**Storage**: PostgreSQL 仅 API 持久实体；网关适配无库。
**Testing**: pytest / go test，先测后实现。
**Contracts**: 本目录 `contracts/` 与 `shared/contracts/` 按需提升。

## Constitution Check

Pre/Post: PASS — 无新微服务；秘密不落明文；整数 usage；TDD。

## Project Structure

```
services/api-service/app/domain/usage/
```

## Complexity Tracking

无豁免。

## Phase 0/1 Summary

research 以源 SF17 + 宪章为准。实现优先领域端口与单测。
