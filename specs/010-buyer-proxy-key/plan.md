# Implementation Plan：买家代理 Key 签发与撤销

**Branch**: `010-buyer-proxy-key` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

## Summary

买家签发平台级代理 Key（只显示一次），绑定买家与 volcano，不绑定单条卖家 Key。 落点 `services/api-service/app/domain/proxykeys/`。

## Technical Context

**Language/Version**: Go 1.25.12 / Python 3.11.15（按落点）
**Storage**: PostgreSQL 仅 API 持久实体；网关适配无库。
**Testing**: pytest / go test，先测后实现。
**Contracts**: 本目录 `contracts/` 与 `shared/contracts/` 按需提升。

## Constitution Check

Pre/Post: PASS — 无新微服务；秘密不落明文；整数 usage；TDD。

## Project Structure

```
services/api-service/app/domain/proxykeys/
```

## Complexity Tracking

无豁免。

## Phase 0/1 Summary

research 以源 SF10 + 宪章为准。实现优先领域端口与单测。
