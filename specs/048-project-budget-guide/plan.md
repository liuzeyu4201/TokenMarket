# Implementation Plan: Project 预算与开发者引导

**Branch**: `048-project-budget-guide` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

买家 Project 页展示账本投影、软/硬预算、原生三协议示例与 checklist。硬阈值与账本可用额取小后拒绝超额预留。无充值提现。

## Technical Context

**Language/Version**: Python 3.11 + React TS

**Contracts**: `project/v1` 1.2.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；金额整数；只读账本。

### Post-Design Gate: PASS

不新增充值；跨服务只经端口读账本。
