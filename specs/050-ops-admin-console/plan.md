# Implementation Plan: 运营管理后台

**Branch**: `050-ops-admin-console` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

admin-service 提供分页运营目录、配置发布管线与高风险向导；前端 `/admin` 独立壳复用设计系统。凭据永不回读。

## Technical Context

**Language/Version**: Python 3.11 + React TS

**Contracts**: `admin-console/v1` 1.0.0

## Constitution Check

### Pre-Research Gate: PASS

契约先行；RBAC 服务端强制。

### Post-Design Gate: PASS

无 SQL 编辑器；审计只追加；admin-service 仍不 migrate。
