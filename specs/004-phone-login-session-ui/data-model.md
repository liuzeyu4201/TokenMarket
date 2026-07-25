# Data Model：手机号验证登录、会话签发与基础界面

**Feature**: `004-phone-login-session-ui`

**Owner**: API Service authentication domain

**System of record**: PostgreSQL 15
**Ephemeral control state**: Redis 7（仅验证码请求限流）

## 设计原则

- PostgreSQL 持有 challenge 消费、幂等首次结果、session 与撤销、安全审计的全部耐久事实。
- Redis 丢失或重启不得让已消费 challenge 或已撤销 session 恢复有效。
- 原手机号、验证码、session token、CSRF token 和原 idempotency key 不写入数据库。
- 所有时间使用服务端 UTC `timestamptz`；到期判断发生在请求事务内，不依赖 cleanup。
- 所有认证 key 均由外部配置注入并带版本；表中只保存 key version 与 HMAC/digest。
- 新表由 additive Alembic `0003_phone_login_session` 创建，不编辑已应用的 `0002`。

## Existing Entity：`users`

SF03 已存在的账户事实，SF04 只读取并锁定，不改变字段或角色枚举。

| Field | Existing type | SF04 use |
|-------|---------------|----------|
| `id` | UUID PK | challenge/session/audit subject |
| `phone_normalized` | varchar(11), unique | 请求时查找 active 用户；不复制到 auth 表 |
| `nickname` | varchar(50) | session summary 只返回当前用户自己的昵称 |
| `role` | `user_role` | 签发时保存 role snapshot；后续授权仍检查当前账户 |
| `status` | active / suspended | 只有 active 可签发和继续使用 session |
| `is_deleted` | boolean | true 时不得签发或继续使用 session |
| `version` | integer | 不作为 session validity 的单独事实 |

**Authentication predicate**:

```text
status == active AND is_deleted == false
```

`deleted` 不是当前 `user_status` 枚举值，任何认证查询都必须同时判断 `is_deleted`。

## Entity 1：`verification_request_idempotency_records`

代表一次“获取验证码”操作的持久幂等占位和首次确定结果。

| Field | Type | Null | Constraints / classification |
|-------|------|------|------------------------------|
| `id` | UUID | no | PK |
| `operation` | varchar(32) | no | V1 固定 `request_verification_code` |
| `key_digest` | bytea | no | HMAC(idempotency key)，敏感校验材料 |
| `key_version` | smallint | no | 外部 HMAC key version |
| `phone_ref` | bytea | no | HMAC(normalized phone)，不可逆个人数据引用 |
| `state` | varchar(16) | no | `processing` / `succeeded` / `failed` |
| `http_status` | smallint | yes | processing 时 null |
| `result_code` | varchar(64) | yes | processing 时 null；稳定业务码 |
| `result_payload` | jsonb | yes | 仅安全响应数据，不含原手机号/OTP/token |
| `created_at` | timestamptz | no | DB time |
| `completed_at` | timestamptz | yes | terminal 时必填 |
| `replay_until` | timestamptz | no | `created_at + 60 seconds` |
| `delete_after` | timestamptz | no | `created_at + 22 hours`，为 24 小时硬期限预留调度缓冲 |

### Constraints and indexes

- UNIQUE (`operation`, `key_version`, `key_digest`).
- CHECK `replay_until > created_at`.
- CHECK `delete_after >= replay_until`.
- CHECK：processing 无 result；terminal 有 `http_status/result_code/completed_at`。
- Index `delete_after`，供 retention worker 小批量清理。
- 同 key + 同 `phone_ref` 且窗口内返回首次结果；同 key + 不同 `phone_ref` 返回
  `IDEMPOTENCY_KEY_CONFLICT`；窗口后返回 `IDEMPOTENCY_KEY_EXPIRED`。

### Lifecycle

```text
processing ── neutral 202 + pending challenge committed ──> succeeded
     └──── validation/rate/provider-wide failure ─────────> failed

succeeded / failed ── replay_until ──> expired-for-replay
expired-for-replay ── delete_after ──> deleted
```

terminal 记录不会重新进入 processing；recipient-specific dispatcher 结果不得改写已持久化
的公开 202 结果。

## Entity 2：`verification_challenges`

代表一次 OTP challenge。`user_id IS NULL` 表示防枚举 decoy，永远不能签发 session。

| Field | Type | Null | Constraints / classification |
|-------|------|------|------------------------------|
| `id` | UUID | no | PK，作为 opaque `challenge_id` 返回 |
| `user_id` | UUID FK users | yes | null = ineligible/decoy |
| `idempotency_record_id` | UUID FK | no | UNIQUE，winner 一对一 |
| `phone_ref` | bytea | no | HMAC(normalized phone) |
| `code_digest` | bytea | yes | terminal 时清空 |
| `code_salt` | bytea | yes | digest 清空时一并清空 |
| `code_key_version` | smallint | yes | OTP key version |
| `provider_request_ref` | UUID | no | UNIQUE，外部 adapter client ref |
| `dispatch_lease_owner` | varchar(64) | yes | 当前 API Service dispatcher 实例的非敏感标识 |
| `dispatch_lease_until` | timestamptz | yes | 仅 pending work 可续租的有界领取期限 |
| `send_started_at` | timestamptz | yes | 外部 send 前提交；非空后禁止再次 send |
| `dispatch_finished_at` | timestamptz | yes | accepted/rejected/timeout/unknown 最终化时间 |
| `attempt_count` | smallint | no | default 0，范围 0–5 |
| `state` | varchar(24) | no | 见状态机 |
| `created_at` | timestamptz | no | DB time |
| `delivered_at` | timestamptz | yes | delivered 时必填 |
| `expires_at` | timestamptz | no | `created_at + 5 minutes` |
| `consumed_at` | timestamptz | yes | consumed 时必填 |
| `invalidated_at` | timestamptz | yes | superseded/locked/failed 时使用 |
| `delete_after` | timestamptz | no | `expires_at + 22 hours`，为 24 小时硬期限预留调度缓冲 |

### State values

| State | Meaning | `code_digest` usable? |
|-------|---------|-----------------------|
| `pending_delivery` | 中性 202 已提交，等待 dispatcher 领取 | no |
| `dispatching` | dispatcher 已提交 send-started 事实，结果未确定 | no |
| `delivered` | 明确 accepted 或 decoy 已建立；仍须检查 user | yes |
| `consumed` | 正确验证码已原子消费 | no |
| `locked` | 第 5 次格式合法但错误的验证码 | no |
| `delivery_failed` | rejected / timeout / unknown | no |
| `superseded` | 新 challenge 使旧 challenge 失效 | no |
| `expired` | 服务端时间达到 `expires_at` | no |

### Constraints and indexes

- CHECK `0 <= attempt_count <= 5`.
- CHECK `expires_at > created_at`.
- CHECK 各 terminal 时间与 state 一致。
- CHECK `send_started_at IS NULL` unless state is
  `dispatching` / `delivered` / `delivery_failed`.
- CHECK `dispatch_finished_at IS NOT NULL` for `delivered` / `delivery_failed`.
- UNIQUE (`idempotency_record_id`), UNIQUE (`provider_request_ref`).
- Partial UNIQUE (`phone_ref`) WHERE state IN (`pending_delivery`, `delivered`)，防止并发
  产生两个当前 challenge。
- Index (`phone_ref`, `created_at DESC`) 用于 rolling 60 秒与 latest challenge。
- Partial index (`state`, `dispatch_lease_until`, `created_at`) WHERE
  `state = 'pending_delivery'`，供 dispatcher 有界领取。
- Index (`state`, `send_started_at`) WHERE `state = 'dispatching'`，供崩溃恢复与积压告警。
- Index (`user_id`, `created_at DESC`) 和 `delete_after`.
- Delivery code：以版本化 key 对 `otp-send:v1 || challenge_id || counter` 做 HMAC，并用
  rejection sampling 无偏派生 6 位 ASCII 数字；仅在请求/dispatcher 进程内短暂存在。
- Verification digest：对 `otp-verify:v1 || challenge_id || code_salt ||
  six_ascii_digits` 做 domain-separated HMAC；比较使用 constant time。
- 仍被 `pending_delivery` / `dispatching` / `delivered` challenge 引用的
  `code_key_version` 不得从配置移除。

### Lifecycle

```text
pending_delivery ── claim + commit send_started ──> dispatching
        ├────────── ineligible decoy finalize ─────> delivered(no provider call)
        ├────────── lease expires before send ─────> pending_delivery
        └────────── newer request ─────────────────> superseded

dispatching ── provider accepted ──────────────────> delivered
        ├──── provider reject/timeout/unknown ─────> delivery_failed
        └──── crash after send_started ────────────> query by provider ref
                                                     or delivery_failed(no resend)

delivered ── correct + eligible ─────> consumed + session
    ├────── correct + decoy ─────────> consumed (no session)
    ├────── wrong attempts 1..4 ─────> delivered(attempt_count + 1)
    ├────── wrong attempt 5 ─────────> locked
    ├────── newer challenge ─────────> superseded
    └────── DB now >= expires_at ────> expired
```

格式不合法的 code 在事务外以 `VALIDATION_ERROR` 拒绝，不增加 `attempt_count`。

## Entity 3：`auth_sessions`

代表一次已验证浏览器登录。Raw opaque token 只存在于 Secure HttpOnly Cookie。

| Field | Type | Null | Constraints / classification |
|-------|------|------|------------------------------|
| `id` | UUID | no | PK；服务端 session identifier |
| `user_id` | UUID FK users | no | owner |
| `token_digest` | bytea | no | HMAC(raw opaque token)，UNIQUE |
| `token_key_version` | smallint | no | current/previous key lookup |
| `role_snapshot` | existing `user_role` | no | 登录时快照；服务端仍查 current status |
| `issued_at` | timestamptz | no | DB time |
| `expires_at` | timestamptz | no | `issued_at + 60 minutes` |
| `revoked_at` | timestamptz | yes | null 表示未显式撤销 |
| `revocation_reason` | varchar(24) | yes | `logout` / `superseded` / `account_disabled` / `expired_cleanup` |
| `created_request_id` | varchar(128) | no | 安全关联，不含凭证 |
| `delete_after` | timestamptz | no | expire/revoke 后 90 天 |

### Constraints and indexes

- UNIQUE (`token_key_version`, `token_digest`).
- Partial UNIQUE (`user_id`) WHERE `revoked_at IS NULL`.
- CHECK `expires_at > issued_at`.
- CHECK `revoked_at IS NULL OR revoked_at >= issued_at`.
- CHECK revocation reason 与 revoked_at 同时为空或同时存在。
- Index (`user_id`, `issued_at DESC`), `expires_at`, `delete_after`.

### Effective status

不持久化可漂移的 active enum；请求时计算：

```text
valid =
  revoked_at IS NULL
  AND expires_at > database_now
  AND users.status == active
  AND users.is_deleted == false
  AND token HMAC matches using a permitted key version
```

自然过期但 `revoked_at IS NULL` 的历史行会在新登录事务中先标记
`expired_cleanup`，再插入新 session；cleanup 不是唯一约束正确性的前提。

### Lifecycle

```text
issued ── logout ─────────────> revoked(logout)
   ├───── newer login ────────> revoked(superseded)
   ├───── account unavailable > revoked(account_disabled) or request-time rejection
   └───── expires_at ─────────> expired (request-time invalid)

expired/revoked ── 90-day retention ──> deleted/anonymized
```

旧 Cookie 的 logout 只按 token digest 撤销自身，不能按 user_id 撤销后来签发的新 session。

## Entity 4：`authentication_security_events`

Append-only 认证安全审计记录。

| Field | Type | Null | Constraints / classification |
|-------|------|------|------------------------------|
| `id` | UUID | no | PK |
| `event_type` | varchar(48) | no | challenge/session/security event |
| `outcome` | varchar(32) | no | success / rejected / failed / suspicious |
| `reason_code` | varchar(64) | no | 低基数稳定值 |
| `request_id` | varchar(128) | no | correlation |
| `user_id` | UUID FK users | yes | ON DELETE SET NULL |
| `challenge_id` | UUID FK challenges | yes | ON DELETE SET NULL |
| `session_id` | UUID FK sessions | yes | ON DELETE SET NULL |
| `subject_ref` | bytea | yes | 可选 HMAC(phone/IP) 引用 |
| `safe_metadata` | jsonb | no | allowlisted keys；禁止原输入与 headers |
| `occurred_at` | timestamptz | no | DB time |
| `delete_after` | timestamptz | no | `occurred_at + 180 days` |

### Required event families

- `challenge_requested`, `challenge_rate_limited`, `delivery_failed`
- `verification_succeeded`, `verification_failed`, `verification_replayed`
- `session_issued`, `session_replaced`, `session_revoked`, `session_rejected`
- `csrf_rejected`, `origin_rejected`, `trusted_proxy_parse_failed`
- `synthetic_provider_blocked`, `auth_secret_invalid`

Index (`event_type`, `occurred_at`) 与 `delete_after`；不得更新业务内容，只允许 retention
删除/匿名化。

## Ephemeral Entity：Redis verification rate-limit buckets

不是 PostgreSQL entity，也不是账户/session 事实。

| Key shape | Data structure | Window / limit |
|-----------|----------------|----------------|
| `tm:{env}:auth:v1:otp:rl:phone:{phone_ref}` | sorted set | rolling 1h / 5 |
| `tm:{env}:auth:v1:otp:rl:ip:{ip_ref}` | sorted set | rolling 1h / 20 |

- `phone_ref` 和 `ip_ref` 均为 HMAC，不出现原手机号/IP。
- Lua 使用 Redis `TIME`、清除窗口外 member、检查两个维度、记录 winner UUID、设置略大于
  1 小时 TTL；任一维度超限返回统一 `RATE_LIMITED`。
- 每个新 idempotency winner 计数一次；窗口内 replay 不重复计数。
- Redis unavailable/script error → request-code path 503；既有 session 验证仍以 PostgreSQL
  继续工作。

## Client-only Entity：Authentication UI State

不是身份事实源，不进入数据库。

```text
AuthState =
  checking
  | anonymous
  | authenticated {
      user_id, nickname, role, phone_masked, expires_at, csrf_token
    }
  | unavailable { request_id? }
```

- 仅 React memory 保存 authenticated summary 与 CSRF。
- `sessionStorage` 可保存：
  `challenge_id`, `phone_masked`, `expires_at`, `resend_available_at`。
- 禁止保存：raw phone、OTP、session Cookie/token、CSRF、完整用户摘要。
- `BroadcastChannel` 只发送 `login/logout/session-invalidated` event name；接收者重新
  `GET /session`。

## Transaction Boundaries

### A. Request verification code

1. Validate body/idempotency header and normalize phone.
2. HMAC idempotency key + phone; insert processing row. Unique loser reads/replays/conflicts.
3. Only winner invokes auth Redis Lua; failure completes deterministic error.
4. Resolve the provider-wide health epoch before account eligibility branching; a failed epoch
   completes one uniform `DELIVERY_UNAVAILABLE` result.
5. Lock eligible user and latest challenge; enforce rolling 60 seconds; supersede old.
6. Generate the challenge id, derive the 6-digit code in memory, persist only its verification
   digest/key version, then insert pending challenge, stable public 202 idempotency result and
   audit; commit.
7. Return HTTP 202 immediately. The request thread never calls the recipient-specific adapter.

### A1. Dispatch pending delivery

1. Dispatcher selects a bounded batch of `pending_delivery` rows using
   `FOR UPDATE SKIP LOCKED`, sets owner/lease, and commits.
2. In a second short transaction, verify the lease and re-read the user. For a decoy, ineligible
   user or changed `phone_ref`, skip send and finalize an externally indistinguishable failed
   state.
3. For an eligible challenge, persist `dispatching` + `send_started_at` and commit before any
   external send.
4. Re-derive the 6-digit code in memory from challenge id/key version, invoke the SMS adapter once
   with the persisted `provider_request_ref`, then discard destination/code; the call is bounded
   to 10 seconds and has no automatic retry.
5. Lock the challenge and finalize accepted as delivered; rejected/timeout/unknown clear OTP
   material and become delivery_failed.
6. If a process dies before `send_started_at`, an expired lease may be reclaimed. If it dies
   after `send_started_at`, recovery may only query by provider ref or invalidate; it must
   never call send again.

No database transaction stays open during provider I/O. Dispatcher shutdown stops new claims
and uses a bounded drain window for already started work.

### B. Verify code and issue session

1. Reject non-ASCII/non-6-digit input before attempt transaction.
2. Resolve challenge subject; lock user, then challenge, using one documented lock order.
3. Recheck user active/not-deleted, challenge delivered/latest/not-expired/attempts.
4. Wrong code: atomic attempt +1; fifth failure locks and clears digest; audit; commit.
5. Correct decoy: consume/clear digest, audit generic failure; no session.
6. Correct eligible: consume/clear digest; revoke all unrevoked user sessions; insert one session;
   audit; commit.
7. Only after commit set session Cookie and return session summary + CSRF.

### C. Authenticate / logout

- Authenticate: parse Cookie version → HMAC raw token → query session + user → evaluate effective
  status; DB failure returns dependency unavailable and never protected data.
- Logout: verify Origin + CSRF; lock exact token digest session; idempotently revoke only that
  session; append audit; commit; clear Cookie with identical attributes.
- Missing/already-invalid Cookie logout returns safe success and clears Cookie without touching a
  different session.

## Retention and Cleanup

| Data | Security validity | Retention action |
|------|-------------------|------------------|
| OTP digest/salt | until terminal or 5m expiry | terminal immediately null；否则 `delete_after = expires_at + 22h` |
| Idempotency replay | 60 seconds | `delete_after = created_at + 22h` |
| Challenge metadata | never valid after terminal/expiry | `delete_after = expires_at + 22h` 后删除/匿名化 |
| Session | 60m unless revoked earlier | delete/anonymize 90d after expiry/revoke |
| Security event | audit only | delete/anonymize after 180d |
| Redis buckets | rolling 1h | TTL slightly >1h |

Cleanup uses small batches, `FOR UPDATE SKIP LOCKED`, a database advisory lock and idempotent
operations. Test and production deployment platforms invoke the API Service one-shot command at
minute 17 of every UTC hour. One invocation has a 15-minute wall-clock budget and processes at
most 500 rows per table per transaction, repeating bounded transactions until no due rows remain
or the budget expires. The 22-hour `delete_after` plus the hourly cadence and runtime budget keeps
the worst planned deletion before the 24-hour hard bound; database time is authoritative.

The stable logical entrypoint is:

```text
python -m app.maintenance.auth_cleanup --batch-size 500 --max-runtime-seconds 900
```

The test/prod scheduler runs this exact module command inside the same-version API Service image.
Local operators invoke it explicitly from the API Service locked environment. There is no second
cleanup wrapper, public Make action, startup loop, or independently versioned maintenance image.

The command records start, finish, outcome, rows by entity and oldest remaining due age without
PII labels. A concurrent invocation that misses the advisory lock exits successfully as
`already_running`. One failure or `last_success >2h` is Warning; three consecutive failures,
`last_success >4h`, or any OTP/challenge/idempotency material crossing its 24-hour hard deadline is
Critical. Oldest due backlog age `>1h` is Warning and `>2h` is Critical. Local development invokes
the same command manually. Startup must not run schema mutation, a cleanup loop or an unbounded
cleanup.

## Migration and Backout

### Upgrade `0003_phone_login_session`

1. Create idempotency table and indexes.
2. Create challenges with FK to users/idempotency.
3. Add dispatch owner/lease/send-started/finalized fields and pending/dispatching recovery indexes.
4. Create sessions and partial unique constraint.
5. Create security events with nullable `ON DELETE SET NULL` audit links.
6. Add cleanup/query indexes.

Use varchar + CHECK state constraints rather than new PostgreSQL enum types to simplify additive
evolution and downgrade. Migration must be repeat-safe through Alembic versioning, not custom
`IF NOT EXISTS` schema mutation.

### Rollback

Preferred application rollback leaves additive tables intact; the previous app ignores them.
Destructive downgrade is only allowed after:

1. auth traffic disabled;
2. all sessions revoked and Cookie expiry window accounted for;
3. security audit retention/export decision approved;
4. event FK dependencies removed in reverse order.

CI evidence uses pinned PostgreSQL 15 and executes upgrade → backout → retry → restore head,
including API/Billing maintained migration ordering.

### Backup and restore evidence

Migration head restoration only proves schema sequencing. Before destructive downgrade or release
claims that rely on recoverability, create a real backup from an isolated PostgreSQL 15 database
containing pending/dispatching/delivered challenges, consumed challenges, active/revoked sessions
and security events; restore it into a fresh database, then verify:

- no consumed challenge becomes usable and no revoked session becomes active;
- `send_started_at` work is queried or invalidated without resend;
- one-active-session, idempotency and retention constraints still hold;
- row counts and safe audit references match the recorded pre-backup manifest.

Evidence contains only opaque IDs/counts and configuration versions, never raw phone, OTP,
Cookie, CSRF or key material.
