# Implementation Plan: 厂商原生花费与多维用量采集

**Branch**: `040-native-spend-usage-capture` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

扩展 `usage/v1` 1.1.0。网关 `usageparse` 按协议解析 JSON/SSE，优先 reported 金额，否则多维 usage；失败 unresolved 且永不填 0。内核在透传响应上挂钩。Billing 校验观察信封。不落账。

## Technical Context

**Language/Version**: Go 1.25.14（解析）+ Python 3.11（Billing 校验）

**Primary Dependencies**: passthrough Kernel、endpcatalog metering_source、usageobs 幂等

**Testing**: Go race；三厂商夹具；SSE；负向；重放；schema 校验

**Contracts**: `usage/v1` 1.1.0 expand-only

## Constitution Check

### Pre-Research Gate: PASS

契约先行；金额用整数微单位；禁止浮点当账。

### Post-Design Gate: PASS

不跨协议转换；证据 digest 不含正文；未知费用非 0。

## Complexity Tracking

无宪章违规。
