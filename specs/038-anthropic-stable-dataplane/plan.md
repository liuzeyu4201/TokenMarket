# Implementation Plan: Anthropic 稳定数据面全兼容

**Branch**: `038-anthropic-stable-dataplane` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

以嵌入目录 anthropic stable 记录为分母做原生透传合同测试；Messages SSE 夹具保序；batches 亲和；控制面/Beta 负向。扩展契约 1.3.0。

## Technical Context

**Language/Version**: Go 1.25.14

**Primary Dependencies**: passthrough Kernel、endpcatalog、affinity

**Testing**: Go testing+race；目录生成表；SSE fixture

**Contracts**: `native-passthrough/v1` 1.3.0 expand-only

## Constitution Check

### Pre-Research Gate: PASS

### Post-Design Gate: PASS

无跨协议转换；Beta 默认关闭。
