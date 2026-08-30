# Implementation Plan: Project 代理 Key 与权限范围

**Branch**: `031-project-proxy-key-scope` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

扩展既有 proxy-keys 域：V0.2 Key 归属 Project，权限 ⊆ Binding。HMAC 存储、一次明文、轮换/禁用/撤销、协议/模型/CIDR/额度/过期交集。网关正向缓存 TTL 改为 1s。历史 volcano 签发保留。

## Technical Context

**Language/Version**: Python 3.11.15、Go 1.25.14（网关缓存 TTL）、TypeScript

**Primary Dependencies**: ProxyKeyService、ProjectService、BindingService、hmac.compare_digest

**Storage**: Alembic `0013_project_proxy_key_scope` 扩展 `proxy_keys` + `proxy_key_quota`

**Testing**: pytest 限制矩阵、并发额度、撤销计时、明文扫描；Go 缓存 TTL；Vitest 签发表单

**Contracts**: 扩 `project/v1` 或沿用 proxy-keys HTTP 并新增 Project 子路径。登记 `project-proxy-key/v1` 1.0.0。

**Security**: 明文不落库；失败同形；CSRF；非 upstream credential

## Constitution Check

### Pre-Research Gate: PASS

契约先行；密钥 HMAC；Postgres SoR；测试先行。

### Post-Design Gate: PASS

不新增服务。不降低撤销 SLA。不把 Key 当连接凭据。

## Complexity Tracking

无宪章违规。
