# Contract：SMS Delivery Port v1

本契约定义 API Service authentication domain 与未来获批准短信供应商 adapter 之间的
最小边界，不选择或承诺具体 vendor。

## Request

```text
SmsDeliveryRequest
  provider_request_ref: UUID       # stable client reference; no retry changes it
  destination: normalized CN phone # exists only in process memory for active user
  code: six ASCII digits           # dispatcher derives it in process memory
  expires_at: UTC timestamp
  template: login_verification_v1
  request_id: correlation id
```

规则：

- `provider_request_ref` 必须在 adapter 调用前持久化且全局唯一。
- code 必须由 dispatcher 使用 challenge id 与持久化 key version 通过批准的
  domain-separated HMAC PRF 无偏重算；不得为异步投递保存 OTP 明文或可逆 ciphertext。
- destination/code 不得写入日志、metric label、exception string、trace attribute 或
  provider metadata 的非秘密字段。
- 超时上限 10 秒；调用方和 adapter 都不得自动 retry send。
- 如果 vendor 支持 client-reference idempotency 或 status query，adapter 必须使用。

## Result

```text
SmsDeliveryResult =
  accepted { safe_provider_ref? }
  | rejected { category }
  | unavailable { category }
  | unknown
```

允许的低基数 category：

- `provider_unavailable`
- `provider_timeout`
- `provider_rejected`
- `configuration_invalid`
- `unknown`

禁止向浏览器透传 vendor error body、recipient state、账户状态、provider credential 或
完整 destination。

## State and recovery

1. HTTP request transaction commits the neutral 202 result, pending challenge and
   `provider_request_ref`, then returns before any recipient-specific adapter call。
2. API Service internal dispatcher claims pending work through PostgreSQL lease semantics。
3. Before calling the adapter, dispatcher commits `dispatching` and `send_started_at`；after that
   point no recovery path may invoke send again for the same `provider_request_ref`。
4. Adapter is invoked at most once per internal idempotency winner and is bounded to 10 seconds。
5. `accepted` is the only result that can make an eligible challenge delivered/usable；
   rejected/timeout/unknown clears OTP digest and produces no usable challenge。
6. Crash recovery:
   - before `send_started_at`: expired work lease may be reclaimed；
   - after `send_started_at`: query status by `provider_request_ref` when supported；
   - otherwise mark failed/unknown and never automatically resend。
7. Graceful shutdown stops new claims and drains started work only within a bounded window。
8. A new user-initiated operation after cooldown uses a new idempotency key, challenge and
   provider reference。

## Anti-enumeration projection

- Provider-wide health is determined before branching by account eligibility and maps uniformly
  to `DELIVERY_UNAVAILABLE`。
- Recipient-specific details never alter public code/message/shape between active and ineligible
  accounts；ineligible requests never send to a real destination。
- Public accepted message is “若账户可用，验证码请求已受理”，not a delivery receipt。
- Public HTTP 202 is committed and returned before recipient-specific dispatch starts；later
  accepted/rejected/timeout/unknown results are internal-only。

## Environment policy

| Mode | Allowed adapter |
|------|-----------------|
| local | ignored-config synthetic adapter |
| test | deterministic fake/synthetic adapter |
| prod | explicitly approved real adapter only |

Production with no approved adapter, synthetic mode, missing secret or invalid timeout fails auth
readiness closed. Synthetic code never appears in response/logs and comes only from ignored local
configuration or injected test fixture。

## Adapter acceptance tests

- exact request mapping and 10-second bound；
- no automatic resend on timeout/unknown；
- public 202 is observable before a deliberately blocked fake adapter is released；
- concurrent dispatchers claim one work item once，and expired pre-send leases recover safely；
- stable provider reference behavior；
- vendor errors mapped to allowed categories；
- log/exception redaction；
- production rejects synthetic/missing configuration；
- process restart before/after `send_started_at` follows reclaim/query-or-invalidate semantics
  without resend；shutdown stops new claims and drains within the configured bound。
