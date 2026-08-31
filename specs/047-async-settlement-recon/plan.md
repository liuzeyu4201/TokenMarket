# Implementation Plan: 异步结算与对账

**Branch**: `047-async-settlement-recon` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 SF28 账本上增加幂等证据事件、未决 case、差额追加、每日对账与带预览的人工冲正。

## Technical Context

**Language/Version**: Python 3.11.15

**Contracts**: `ledger/v1` 1.2.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；整数金额；分录只追加。

### Post-Design Gate: PASS

未决不归零；冲正只追加；价格版本沿用 reservation。
