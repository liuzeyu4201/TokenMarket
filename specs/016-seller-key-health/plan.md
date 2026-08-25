# Implementation Plan：卖家 Key 周期健康检查

**Branch**: `016-seller-key-health` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

用 SF06 分类更新 health_state；临时类不得覆盖为永久 invalid。 落点 `services/proxy-gateway/internal/domain/keyhealth/`。

## Technical Context

**Language/Version**: Go 1.25.12 / Python 3.11.15（按落点）
**Storage**: PostgreSQL 仅 API 持久实体；网关适配无库。
**Testing**: pytest / go test，先测后实现。
**Contracts**: 本目录 `contracts/` 与 `shared/contracts/` 按需提升。

## Constitution Check

Pre/Post: PASS — 无新微服务；秘密不落明文；整数 usage；TDD。

## Project Structure

```
services/proxy-gateway/internal/domain/keyhealth/
```

## Complexity Tracking

无豁免。

## Phase 0/1 Summary

research 以源 SF16 + 宪章为准。实现优先领域端口与单测。
