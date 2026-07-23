# Data Model: 用户注册与初始界面

**Feature**: `003-user-registration-ui`  
**Date**: 2026-07-23  
**Source of truth**: PostgreSQL via **API Service** ownership  
**Ephemeral control plane**: Redis registration rate-limit buckets  

## Overview

```text
Client (Browser)
  └── Registration Form Session (ephemeral UI state)
        │
        ▼ HTTP + Idempotency-Key + X-Request-ID
API Service
  ├── PhoneNormalizer (pure)
  ├── RateLimiter ── Redis buckets (ip / phone_normalized)
  └── RegistrationService
        └── short DB transaction
              ├── users
              └── registration_idempotency_records
```

## Entity: User（表 `users`）

账户权威实体。本功能只 **创建** active 用户；不登录、不改角色、不硬删除。

| Field | Type | Constraints | Notes |
|-------|------|-------------|--------|
| `id` | UUID | PK, server-generated | 对外用户标识 |
| `phone_normalized` | VARCHAR(11) | UNIQUE NOT NULL, CHECK `^1[3-9][0-9]{9}$` | 仅存规范化结果 |
| `nickname` | VARCHAR(50) | NOT NULL | 去首尾空白后 1–50 可显示字符 |
| `role` | ENUM `user_role` | NOT NULL | `buyer` \| `seller` \| `both` |
| `status` | ENUM `user_status` | NOT NULL DEFAULT `active` | 本功能只写 `active` |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | UTC |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | UTC |
| `is_deleted` | BOOLEAN | NOT NULL DEFAULT false | 软删除 |
| `version` | INTEGER | NOT NULL DEFAULT 1 | 乐观锁，创建为 1 |

### Invariants

1. **全局手机号唯一**：`UNIQUE (phone_normalized)` 覆盖软删除行；禁止同号第二账户。
2. 新建：`status = active`、`is_deleted = false`、`version = 1`。
3. 不存储密码、邮箱、明文国家码前缀或原始输入串（原始串仅用于规范化输入，不落库）。
4. 软删除后：`is_deleted = true`；再注册不得 INSERT，服务层返回 `ACCOUNT_UNAVAILABLE`。

### State transitions (this feature)

```text
(none) --register--> active, is_deleted=false
```

Soft-delete / suspend / restore：out of scope（后续功能）。

### Classification

- **PII**: `phone_normalized`（高敏感）、`nickname`（中低）。
- **Owner**: API Service.
- **Retention**: 遵循平台账户保留策略；本功能不定义硬删作业。软删保留至平台删除策略执行前。
- **Backup / restore**: 与 API Service 所用 PostgreSQL 实例共用平台备份与非生产 restore；无特性级独立备份。幂等表非账户事实源，24h 后可清理。
- **Audit**: 创建时间与后续更新时间必填；不在日志打印完整手机号。

## Entity: RegistrationIdempotencyRecord（表 `registration_idempotency_records`）

| Field | Type | Constraints | Notes |
|-------|------|-------------|--------|
| `id` | UUID | PK | 内部 |
| `idempotency_key` | VARCHAR(64) | UNIQUE NOT NULL | 客户端键 |
| `request_hash` | CHAR(64) | NOT NULL | hex SHA-256 of canonical request |
| `user_id` | UUID | NULL FK → users.id | 成功创建时必填 |
| `result_code` | VARCHAR(64) | NOT NULL | 业务码，如 `0` |
| `result_payload` | JSONB | NOT NULL | 成功时的 `data` 快照（无完整手机号） |
| `created_at` | TIMESTAMPTZ | NOT NULL | 首次受理 |
| `expires_at` | TIMESTAMPTZ | NOT NULL | `created_at + interval '24 hours'` |

### Invariants

1. 同一 `idempotency_key` 仅一行。
2. 窗口内重放：键存在且 `now < expires_at` 且 hash 相同 → 返回存储的成功包络。
3. 窗口内 hash 不同 → `IDEMPOTENCY_KEY_CONFLICT`，不改用户表。
4. `now >= expires_at` → `IDEMPOTENCY_KEY_EXPIRED`，不返回 `result_payload` 作为成功。
5. 不保存原始手机号或完整请求明文；`request_hash` 基于规范化字段。

### Canonical request hash input

```text
phone_normalized | nickname_stripped | role
```

UTF-8，固定分隔符，SHA-256 hex。

## Entity: RegistrationRateLimitBucket（Redis，非 DB 表）

| Dimension | Key pattern | Limit | Window |
|-----------|-------------|-------|--------|
| IP | `reg:rl:ip:{ip}` | 20 | 15 minutes |
| Phone | `reg:rl:phone:{phone_normalized}` | 5 | 15 minutes |

- Value: integer counter.
- TTL: 900 seconds on first increment.
- Not a source of truth for accounts.
- Phone dimension only after successful normalize; invalid phones may still count on IP dimension.

## Entity: RegistrationFormSession（客户端，非持久）

| Field | Notes |
|-------|--------|
| phone input | 控件内，不写入 localStorage |
| nickname | 控件内 |
| role | 三选一，无默认也可，实施选“无预选强制选择” |
| idempotency_key | 本次提交生成；重试复用直至成功或换新提交 |
| ui phase | editing \| submitting \| success \| error |
| field errors | 映射服务端字段错误 |
| request_id | 最近一次响应 |

刷新可丢失；不得作为账户是否存在的依据。

## Validation rules (server authority)

| Field | Rules |
|-------|--------|
| phone | FR-002a–c 规范化后 11 位大陆号 |
| nickname | trim；长度 1–50；无 C0/C1 控制字符与换行 |
| role | enum 三值 |
| idempotency_key | 非空，≤64，建议 UUID；非法则 400 |

## Relationships

- `RegistrationIdempotencyRecord.user_id` → `User.id`（成功路径）。
- Rate-limit buckets 无 FK；按字符串维度关联。

## Migration sketch

Revision after `0001_baseline`:

1. CREATE TYPE `user_role`, `user_status`.
2. CREATE TABLE `users` + UNIQUE phone + checks.
3. CREATE TABLE `registration_idempotency_records` + UNIQUE key + FK + index on `expires_at`.
4. Downgrade drops tables/types in reverse order.

## Concurrency

- Unique on `phone_normalized` + unique on `idempotency_key` provide last-line integrity.
- Service: begin → optional idempotency lookup → insert user → insert idempotency → commit.
- On unique violation: map to `PHONE_ALREADY_REGISTERED` or re-read soft-deleted → `ACCOUNT_UNAVAILABLE`；或幂等键冲突路径。
