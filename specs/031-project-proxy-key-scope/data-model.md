# Data Model：Project 代理 Key

## ProxyKey（扩展）

| 字段 | 约束 |
|------|------|
| id | UUID PK |
| buyer_id | UUID |
| project_id | UUID NULL FK projects；V0.2 NOT NULL 在应用层 |
| platform | volcano（旧）或 project |
| secret_hash | HMAC hex UNIQUE |
| masked_prefix / masked_suffix | 展示用 |
| name | 可选 |
| status | active \| disabled \| revoked |
| protocols | TEXT[] |
| allowed_models | TEXT[] |
| allowed_cidrs | TEXT[] |
| quota_period | day \| month \| NULL |
| quota_limit | INT NULL |
| expires_at | timestamptz NULL |
| revoked_at / disabled_at / rotated_at | timestamptz |

不变量：revoked 不可再 active。secret 明文不存储。

## ProxyKeyQuota

| 字段 | 约束 |
|------|------|
| key_id | UUID |
| period_start | timestamptz |
| accepted | INT ≥0 |

PK `(key_id, period_start)`。`accepted < quota_limit` 才递增。

## AuthorizeInput

protocol、model、client_ip、now。失败不区分原因。
