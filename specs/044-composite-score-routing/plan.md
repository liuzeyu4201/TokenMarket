# Implementation Plan: 综合评分路由

**Branch**: `044-composite-score-routing` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 SF23 合格集上按不可变 policy 对健康/延迟/容量/价格整数加权；缺测为 0；可重放；ScoringSelector 先 Filter 再 Rank。

## Technical Context

**Language/Version**: Go 1.25.14

**Contracts**: `route-decision/v1` 1.2.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；测试先行。

### Post-Design Gate: PASS

不绕过硬门槛；金额/权重用整数。
