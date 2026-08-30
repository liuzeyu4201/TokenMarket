# Data Model：统一手机号验证

## VerificationChallenge（扩展）

| 字段 | 约束 |
|------|------|
| phone_normalized | VARCHAR(11) NULL；仅注册用途挑战非空 |

不变量：`phone_normalized IS NOT NULL` ⇒ 可投递注册 OTP；`user_id IS NULL AND phone_normalized IS NULL` ⇒ decoy。

## ProfileCompletionIntent

| 字段 | 约束 |
|------|------|
| id | UUID PK |
| phone_normalized | CHAR/VARCHAR(11) NOT NULL |
| challenge_id | UUID，已消费挑战 |
| token_digest | BYTEA UNIQUE |
| token_key_version | SMALLINT |
| expires_at | timestamptz |
| consumed_at | timestamptz NULL |
| created_at | timestamptz |

部分唯一：未消费且未过期的同一 `phone_normalized` 至多一条（可用部分索引）。TTL 建议 10 分钟。

## User / AuthSession

无新列。User 只在补全事务插入。
