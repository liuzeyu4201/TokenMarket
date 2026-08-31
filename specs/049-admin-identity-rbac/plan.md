# Implementation Plan: 管理员身份与审计

**Branch**: `049-admin-identity-rbac` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 admin-service 建立独立身份 Cookie、RBAC 矩阵、高风险 step-up 与哈希链追加审计。不拥有用户库，不迁移用户角色为 admin。

## Technical Context

**Language/Version**: Python 3.11.15

**Contracts**: `admin-identity/v1` 1.0.0；`audit/v1` 1.1.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；最小权限；密钥脱敏。

### Post-Design Gate: PASS

admin-service 仍不绑定 migrate；审计内存哈希链 + 应用层禁改删。
