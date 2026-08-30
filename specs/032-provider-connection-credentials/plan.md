# Implementation Plan: Provider Connection 与凭据安全

**Branch**: `032-provider-connection-credentials` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

卖家 Connection 域：三厂商凭据 envelope 加密、不可逆指纹、无公开读回、内部 unwrap、SSRF allowlist、整体替换与删除销毁。复用 `CredentialEncryptor`。扩展 `provider-connection/v1`。注入 Binding `ConnectionLookup`。

## Technical Context

**Language/Version**: Python 3.11.15、TypeScript

**Primary Dependencies**: CredentialEncryptor、fingerprint_key、Authorization 工作区透镜

**Storage**: Alembic `0014_provider_connections`

**Testing**: pytest 明文扫描、unwrap 负向、SSRF 矩阵、并发替换、轮换解密、删除；Vitest 表单不回显

**Contracts**: `provider-connection/v1` 1.1.0 expand-only

**Security**: 内部令牌 unwrap；审计无明文；SSRF fail-closed

## Constitution Check

### Pre-Research Gate: PASS

契约先行；密钥不落库明文；测试先行。

### Post-Design Gate: PASS

不新增 KMS 服务（版本化密钥环即 envelope 接口）。不实现厂商控制面。

## Complexity Tracking

无宪章违规。
