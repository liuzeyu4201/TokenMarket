# Implementation Plan: 统一手机号验证注册登录

**Branch**: `025-unified-phone-auth` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

将 V0.1 分离的「无 OTP 注册」与「仅已注册登录」收成一条手机号验证码入口：验证前中性 202；OTP 后 active 用户发会话，未知号码发短时补全凭证；昵称+角色原子建号并自动登录。公开无凭证 `POST /register` 拒绝以防枚举。

## Technical Context

**Language/Version**: Python 3.11.15（api-service）、TypeScript 严格（frontend）

**Primary Dependencies**: 既有 ChallengeService / SessionService / RegistrationService / Synthetic SMS / HttpOnly cookie

**Storage**: PostgreSQL — `verification_challenges.phone_normalized` 可空列；`profile_completion_intents` 新表。Alembic `0008_unified_phone_auth`。

**Testing**: pytest 单元/集成（含 50 并发）；Vitest 前端；负向 OTP；日志无 OTP。

**Affected Components**: `services/api-service/`、`frontend/src/`、`shared/contracts/unified-phone-auth/v1/`

## Constitution Check

### Pre-Research Gate: PASS

OTP 不落库明文；补全凭证 host-only cookie；契约先行；users 唯一约束；无密码。

### Post-Design Gate: PASS

expand 迁移；旧 register HTTP 拒绝；停用账户仍 decoy。

## Project Structure

```text
shared/contracts/unified-phone-auth/v1/
services/api-service/alembic/versions/0008_unified_phone_auth.py
services/api-service/app/domain/authentication/
frontend/src/pages/Login.tsx  # 统一入口
frontend/src/pages/Register.tsx
```

## Complexity Tracking

无宪章违规。
