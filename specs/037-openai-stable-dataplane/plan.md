# Implementation Plan: OpenAI 稳定数据面全兼容

**Branch**: `037-openai-stable-dataplane` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

以嵌入 Endpoint Catalog 为唯一范围，对全部 openai `stability=stable` 记录做原生透传合同测试；控制面/未登记/shared+stateful 负向覆盖。扩展 `native-passthrough/v1` 1.2.0。不新增路由或转换层。

## Technical Context

**Language/Version**: Go 1.25.14

**Primary Dependencies**: passthrough Kernel、endpcatalog LoadEmbedded、affinity Table

**Testing**: Go testing+race；目录生成表；夹具差分；env 门禁真实冒烟

**Contracts**: `native-passthrough/v1` 1.2.0 expand-only

## Constitution Check

### Pre-Research Gate: PASS

契约先行；测试先行；不新增服务。

### Post-Design Gate: PASS

不手写端点白名单；不跨协议转换；真实付费冒烟不默认执行。

## Complexity Tracking

无宪章违规。
