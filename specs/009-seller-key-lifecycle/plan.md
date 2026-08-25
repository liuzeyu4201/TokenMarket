# Implementation Plan：卖家 API Key 生命周期

**Branch**: `009-seller-key-lifecycle` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

暂停/恢复/撤销；administrative_state 与 health_state 分离；revoked 终态擦除密文。 落点 `services/api-service/app/domain/sellerkeys/lifecycle.py`。

## Technical Context

**Language/Version**: Go 1.25.12 / Python 3.11.15（按落点）
**Storage**: PostgreSQL 仅 API 持久实体；网关适配无库。
**Testing**: pytest / go test，先测后实现。
**Contracts**: 本目录 `contracts/` 与 `shared/contracts/` 按需提升。

## Constitution Check

Pre/Post: PASS — 无新微服务；秘密不落明文；整数 usage；TDD。

## Project Structure

```
services/api-service/app/domain/sellerkeys/lifecycle.py
```

## Complexity Tracking

无豁免。

## Phase 0/1 Summary

research 以源 SF09 + 宪章为准。实现优先领域端口与单测。
