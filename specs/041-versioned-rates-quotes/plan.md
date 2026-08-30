# Implementation Plan: 版本化费率、买家倍率与卖家报价

**Branch**: `041-versioned-rates-quotes` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

扩展 `pricing/v1` 1.1.0。Billing 整数报价引擎：draft→preview→approve→publish，锁定版本重算。Gateway 在请求接受时快照 rate/buyer/seller 版本。published 不可变。

## Technical Context

**Language/Version**: Python 3.11（引擎）+ Go 1.25.14（锁）

**Primary Dependencies**: usage/v1 capture、整数微单位

**Testing**: pytest 黄金舍入/发布负向；Go race 并发切换

**Contracts**: `pricing/v1` 1.1.0 expand-only

## Constitution Check

### Pre-Research Gate: PASS

契约先行；金额整数；禁止浮点入账。

### Post-Design Gate: PASS

无充值/法币；未知费率 unresolved；已锁请求不追溯。

## Complexity Tracking

无宪章违规。
