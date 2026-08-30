# Implementation Plan: 专享绑定失败关闭

**Branch**: `045-dedicated-binding-fail-closed` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

dedicated Project 固定一条 Connection；异常失败关闭且不回退共享池。人工更换需确认与影响清单，原子切换，旧连接 draining。

## Technical Context

**Language/Version**: Go 1.25.14（网关）+ Python 3.11（API）

**Contracts**: `provider-binding/v1` 1.1.0；`native-passthrough/v1` 1.5.0 增加 `DEDICATED_UNAVAILABLE`

## Constitution Check

### Pre-Research Gate: PASS

契约先行；失败关闭；不跨协议。

### Post-Design Gate: PASS

不自动 failover；金额/状态用显式枚举；审计必记。
