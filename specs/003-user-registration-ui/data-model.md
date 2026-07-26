# 数据模型：用户注册与初始界面

**特性**: `003-user-registration-ui`
**日期**: 2026-07-23
**事实源**: PostgreSQL，由 **API Service** 拥有
**短暂控制面**: Redis 注册限流桶

## 概览

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

## 实体：User（表 `users`）

账户权威实体。本功能只 **创建** active 用户；不登录、不改角色、不硬删除。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK，服务端生成 | 对外用户标识 |
| `phone_normalized` | VARCHAR(11) | UNIQUE NOT NULL，CHECK `^1[3-9][0-9]{9}$` | 仅存规范化结果 |
| `nickname` | VARCHAR(50) | NOT NULL | 去首尾空白后 1–50 可显示字符 |
| `role` | ENUM `user_role` | NOT NULL | `buyer` \| `seller` \| `both` |
| `status` | ENUM `user_status` | NOT NULL DEFAULT `active` | 本功能只写 `active` |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | UTC |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | UTC |
| `is_deleted` | BOOLEAN | NOT NULL DEFAULT false | 软删除 |
| `version` | INTEGER | NOT NULL DEFAULT 1 | 乐观锁，创建为 1 |

### 不变量

1. **全局手机号唯一**：`UNIQUE (phone_normalized)` 覆盖软删除行；禁止同号第二账户。
2. 新建：`status = active`、`is_deleted = false`、`version = 1`。
3. 不存储密码、邮箱、明文国家码前缀或原始输入串（原始串仅用于规范化输入，不落库）。
4. 软删除后：`is_deleted = true`；再注册不得 INSERT，服务层返回 `ACCOUNT_UNAVAILABLE`。

### 状态迁移（本特性）

```text
(none) --register--> active, is_deleted=false
```

软删除 / 暂停 / 恢复：out of scope（后续功能）。

### 分类

- **PII**: `phone_normalized`（高敏感）、`nickname`（中低）。
- **Owner**: API Service。
- **保留**: 遵循平台账户保留策略；本功能不定义硬删作业。软删保留至平台删除策略执行前。
- **备份 / 恢复**: 与 API Service 所用 PostgreSQL 实例共用平台备份与非生产 restore；无特性级独立备份。幂等表非账户事实源，24h 后可清理。
- **审计**: 创建时间与后续更新时间必填；不在日志打印完整手机号。

## 实体：RegistrationIdempotencyRecord（表 `registration_idempotency_records`）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 内部 |
| `idempotency_key` | VARCHAR(64) | UNIQUE NOT NULL | 客户端键 |
| `request_hash` | CHAR(64) | NOT NULL | 规范请求的 hex SHA-256 |
| `user_id` | UUID | NULL FK → users.id | 成功创建时必填 |
| `result_code` | VARCHAR(64) | NOT NULL | 业务码，如 `0` |
| `result_payload` | JSONB | NOT NULL | 成功时的 `data` 快照（无完整手机号） |
| `created_at` | TIMESTAMPTZ | NOT NULL | 首次受理 |
| `expires_at` | TIMESTAMPTZ | NOT NULL | `created_at + interval '24 hours'` |

### 不变量

1. 同一 `idempotency_key` 仅一行。
2. 窗口内重放：键存在且 `now < expires_at` 且 hash 相同 → 返回存储的成功包络。
3. 窗口内 hash 不同 → `IDEMPOTENCY_KEY_CONFLICT`，不改用户表。
4. `now >= expires_at` → `IDEMPOTENCY_KEY_EXPIRED`，不返回 `result_payload` 作为成功。
5. 不保存原始手机号或完整请求明文；`request_hash` 基于规范化字段。

### 规范请求哈希输入

```text
phone_normalized | nickname_stripped | role
```

UTF-8，固定分隔符，SHA-256 hex。

## 实体：RegistrationRateLimitBucket（Redis，非 DB 表）

| 维度 | 键模式 | 上限 | 窗口 |
|------|--------|------|------|
| IP | `reg:rl:ip:{ip}` | 20 | 15 分钟 |
| 手机号 | `reg:rl:phone:{phone_normalized}` | 5 | 15 分钟 |

- 值：整型计数器。
- TTL：首次递增时 900 秒。
- 非账户事实源。
- 手机号维度仅在规范化成功后计数；非法手机号仍可计入 IP 维度。

## 实体：RegistrationFormSession（客户端，非持久）

| 字段 | 说明 |
|------|------|
| phone 输入 | 控件内，不写入 localStorage |
| nickname | 控件内 |
| role | 三选一，无默认也可，实施选“无预选强制选择” |
| idempotency_key | 本次提交生成；重试复用直至成功或换新提交 |
| ui 阶段 | editing \| submitting \| success \| error |
| 字段错误 | 映射服务端字段错误 |
| request_id | 最近一次响应 |

刷新可丢失；不得作为账户是否存在的依据。

## 校验规则（服务端权威）

| 字段 | 规则 |
|------|------|
| phone | FR-002a–c 规范化后 11 位大陆号 |
| nickname | trim；长度 1–50；无 C0/C1 控制字符与换行 |
| role | 枚举三值 |
| idempotency_key | 非空，≤64，建议 UUID；非法则 400 |

## 关系

- `RegistrationIdempotencyRecord.user_id` → `User.id`（成功路径）。
- 限流桶无 FK；按字符串维度关联。

## 迁移草图

接在 `0001_baseline` 之后的修订：

1. CREATE TYPE `user_role`、`user_status`。
2. CREATE TABLE `users` + UNIQUE phone + checks。
3. CREATE TABLE `registration_idempotency_records` + UNIQUE key + FK + `expires_at` 索引。
4. Downgrade 按逆序 drop 表/类型。

## 并发

- `phone_normalized` 唯一与 `idempotency_key` 唯一提供最后防线完整性。
- 服务：begin → 可选幂等查找 → insert user → insert 幂等 → commit。
- 唯一性冲突：映射为 `PHONE_ALREADY_REGISTERED`，或重读软删除 → `ACCOUNT_UNAVAILABLE`；或幂等键冲突路径。
