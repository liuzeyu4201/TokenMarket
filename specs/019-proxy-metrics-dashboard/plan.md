# Implementation Plan：代理运行指标与基础看板

**Branch**: `019-proxy-metrics-dashboard` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

Prometheus 指标 provider_chat_* / provider_validate_*；Grafana 由 SF02 生命周期提供。 落点 `services/proxy-gateway/internal/observability/`。

## Technical Context

**Language/Version**: Go 1.25.12 / Python 3.11.15（按落点）
**Storage**: PostgreSQL 仅 API 持久实体；网关适配无库。
**Testing**: pytest / go test，先测后实现。
**Contracts**: 本目录 `contracts/` 与 `shared/contracts/` 按需提升。

## Constitution Check

Pre/Post: PASS — 无新微服务；秘密不落明文；整数 usage；TDD。

## Project Structure

```
services/proxy-gateway/internal/observability/
```

## Complexity Tracking

无豁免。

## Phase 0/1 Summary

research 以源 SF19 + 宪章为准。实现优先领域端口与单测。
