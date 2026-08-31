# Implementation Plan: 不可变账本与同步结算

**Branch**: `046-immutable-ledger-settlement` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

Billing Service 以整数测试额度做原子预留、同步平衡结算、释放与冲正；分录只追加；余额为可重建投影。

## Technical Context

**Language/Version**: Python 3.11.15（Billing）+ Go 1.25.14（网关可选预留钩子）

**Contracts**: `ledger/v1` 1.1.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；金额用整数；幂等；不可变账本。

### Post-Design Gate: PASS

禁止浮点金额；禁止 UPDATE 修余额；无充值/提现。
