# Implementation Plan: 全链路可观测、SLO 与告警处置

**Branch**: `051-observability-slo-alerts` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在既有 Prometheus/Grafana 与 request ID 中间件上增加全链路 hops、有界 RED、平台/upstream 时延拆分、SLO 错误预算与五类可执行告警。密钥永不进入遥测。

## Technical Context

**Language/Version**: Go 1.25.14 + Python 3.11

**Contracts**: `observability/v1` 1.0.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；相关 ID 跨边界；脱敏在序列化前。

### Post-Design Gate: PASS

无 user/project/request ID 作无界 label；不记录 prompt/凭据；admin-service 仍不 migrate。
