# Data Model：火山方舟凭证与额度验证

**Feature**: `006-volcano-key-validation`  
**Owner**: Proxy Gateway（`services/proxy-gateway/`）  
**System of record**: **无** — 本功能不持久化任何实体  
**Ephemeral**: 单次请求内存中的输入/结果；进程内并发闸门计数

## 设计原则

- 原始凭证为高价值机密：仅验证期间驻留内存，用后不可达，永不落盘（本功能范围）。
- 验证结果为**值对象**，由调用方（SF08/SF16）决定是否持久化及如何与历史事实合并。
- 额度仅在可信官方源可读时有值；否则字段为空，禁止用 0 表示未知。
- 时间：`checked_at` 使用 RFC3339 UTC。
- 额度：整数基础单位或精确十进制字符串 + `quota_unit`；禁止 IEEE754 二进制浮点表示价值。

## Entity 1：Provider Credential Input（瞬时）

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `platform` | string | yes | V0.1 仅 `volcano`；其他 → `unsupported_platform` |
| `api_key` | string | yes | 完整密钥；仅内存；不得记入日志 |
| `request_id` | string | yes | 关联遥测；调用方传入或网关生成 |

**Invariants**:

- `api_key` 非空、去首尾空白后仍非空。
- 不得作为 DB 行或缓存 value 存储。

**Lifecycle**: 请求开始创建 → 出站调用使用 → 返回前丢弃引用。

## Entity 2：Credential Validation Result（值对象）

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `platform` | string | yes | 回显规范化平台 ID |
| `validity` | enum | yes | `valid` \| `invalid` \| `unknown` |
| `availability` | enum | yes | `available` \| `unavailable` |
| `remaining_quota` | decimal/int string or null | conditional | 仅可信额度可读时有值；`quota_unavailable` 时 **必须 null/omit** |
| `quota_unit` | string or null | conditional | 与额度同时出现；如 `CNY_fen` / 官方单位名（启用额度后由契约固定） |
| `supported_models` | string[] | yes | 可为 `[]`；仅为 V0.1 allowlist 交集 |
| `checked_at` | string (RFC3339) | yes | 验证完成时刻 UTC |
| `error_category` | enum | yes | 见下表 |
| `retry_after_seconds` | positive int | when rate_limited | 缺省策略见 research D6 |
| `credential_ref` | string | optional | 不可逆短哈希前缀，仅遥测；**不得**可逆还原 Key |
| `suggested_action` | enum | optional | 机器可读：`fix_credential` \| `add_quota` \| `enable_models` \| `retry_later` \| `unsupported` |

### `error_category` 枚举

`success` · `invalid` · `forbidden` · `zero_quota` · `quota_unavailable` ·
`no_supported_models` · `rate_limited` · `temporary_unavailable` · `timeout` ·
`invalid_response` · `unsupported_platform`

### 结果组合不变量

| error_category | validity | availability | remaining_quota | retry_after_seconds |
|----------------|----------|--------------|-----------------|---------------------|
| success | valid | available | > 0 且非 null | omit |
| zero_quota | valid | unavailable | 0 | omit |
| quota_unavailable | valid 或 unknown* | unavailable | **null** | omit |
| no_supported_models | valid | unavailable | 若已读到则保留 | omit |
| invalid | invalid | unavailable | null | omit |
| forbidden | invalid | unavailable | null | omit |
| rate_limited | valid 或 unknown* | unavailable | null 或保留当次 | **required ≥1** |
| temporary_unavailable | unknown | unavailable | null | optional |
| timeout | unknown | unavailable | null | optional |
| invalid_response | unknown | unavailable | null | omit |
| unsupported_platform | invalid 或 unknown | unavailable | null | omit |

\* 当次已用 200 证明鉴权成功则为 `valid`；否则 `unknown`。  
`success` 还要求 `supported_models` 非空。

## Entity 3：Provider Error Classification（逻辑枚举）

非独立存储。映射规则见 [research.md](./research.md) Decision 4 与
[contracts/error-classification.md](./contracts/error-classification.md)。

**Consumer merge rules（非本实体状态机，供 SF08/SF16）**:

```text
on new_result:
  if new.error_category in {invalid, forbidden}:
      may set persisted_auth = invalid
  else if new.error_category in {
      rate_limited, temporary_unavailable, timeout,
      quota_unavailable, no_supported_models, invalid_response
  }:
      MUST NOT set persisted_auth = invalid from this result alone
  # success / zero_quota 更新健康与额度策略由 SF08/SF16 定义
```

## Entity 4：Concurrency Gate State（进程内瞬时）

| Field | Type | Notes |
|-------|------|-------|
| global_in_flight | int | 0..global_limit |
| per_credential_in_flight | map[credential_gate_key]int | key = HMAC/hash(api_key)，非明文 |

**Defaults**: global_limit=32，per_credential_limit=1。  
**Persistence**: 无；进程重启清零。

## Entity 5：V0.1 Chat Model Allowlist（配置）

| Field | Type | Notes |
|-------|------|-------|
| model_ids | set[string] | 配置或默认文件 |

与上游模型 ID 求交得到 `supported_models`。

## Relationships

```text
CredentialInput --(validate)--> CredentialValidationResult
Volcano upstream models response --(parse+intersect)--> supported_models
Volcano upstream quota response --(optional future)--> remaining_quota
ConcurrencyGate --(admit/reject)--> validate pipeline
```

## Persistence & Migrations

**N/A** — 无表、无 Alembic/Go migrate。  
回滚 = 关闭内部路由 / 回退网关镜像。

## Classification

| Data | Class | Handling |
|------|-------|----------|
| api_key | secret (reversible high value) | memory only; redaction |
| credential_ref | internal telemetry | irreversible |
| validation result | business sensitive | caller-owned if stored |
| model ids | public-ish | ok in logs at info carefully |
