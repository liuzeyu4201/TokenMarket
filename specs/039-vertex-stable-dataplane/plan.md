# Implementation Plan: Google Vertex 稳定数据面全兼容

**Branch**: `039-vertex-stable-dataplane` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

目录生成 vertex stable 合同测试；operation `name` 亲和；ResourceID 跳过 project/location/publisher/model；控制面负向。契约 1.4.0。

## Technical Context

**Language/Version**: Go 1.25.14

**Contracts**: `native-passthrough/v1` 1.4.0 expand-only

## Constitution Check

### Pre-Research Gate: PASS

### Post-Design Gate: PASS
