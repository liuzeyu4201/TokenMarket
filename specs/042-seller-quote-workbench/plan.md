# Implementation Plan: 卖家受限报价与供给工作台

**Branch**: `042-seller-quote-workbench` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

API-service Workbench 领域：连接级报价追加版本、容量、审计、限流、隐私视图。前端卖家 `/supply`。复用 SF16 暂停/排空与 SF27 bps 边界。

## Technical Context

**Language/Version**: Python 3.11 + React TS

**Primary Dependencies**: Connection lifecycle、pricing bps 边界

**Testing**: pytest HTTP/领域；vitest 工作台

**Contracts**: `seller-workbench/v1` 1.0.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；不回读凭据；测试额度不可兑。

### Post-Design Gate: PASS

无买家倍率泄漏；无负价差；账本未就绪不把 unresolved 记 settled。
