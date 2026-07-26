# Contract：Phone Authentication Business Codes v1

**Owner**: API Service

**Envelope**: `{code, message, data, request_id, timestamp}`

**OpenAPI**: [phone-auth-session.openapi.yaml](./phone-auth-session.openapi.yaml)

客户端必须以稳定 `code` 决定交互，不得仅按 HTTP status 或直接展示任意服务端 message。

| Code | HTTP | Endpoint(s) | Client action | Security semantics |
|------|------|-------------|---------------|--------------------|
| `0` | 200/202 | all | 读取 contracted data | request challenge 的 202 不证明账户存在或实际送达 |
| `VALIDATION_ERROR` | 400 | challenge/session | 修复字段 | 非 6 位 ASCII code 不消耗失败次数 |
| `ORIGIN_REJECTED` | 403 | browser writes | 阻止并显示安全失败 | 不透露 allowlist 内容 |
| `CSRF_INVALID` | 403 | logout/future writes | 重新 bootstrap；不得自动重放写操作 | 无状态变化 |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | challenge | 为独立操作生成新 key | 不投递 |
| `IDEMPOTENCY_KEY_CONFLICT` | 409 | challenge | 不复用该 key，检查手机号后新建操作 | 同 key 异 phone_ref |
| `IDEMPOTENCY_KEY_EXPIRED` | 409 | challenge | 新建 key 后由用户再次发送 | 旧结果不再 replay |
| `RATE_LIMITED` | 429 | challenge | 依 `retry_after_seconds` 等待 | 不暴露 phone/IP 哪个维度超限 |
| `VERIFICATION_FAILED` | 401 | create session | `retry_code` 或 `request_new_code` | 不能创建 session |
| `CHALLENGE_UNAVAILABLE` | 409 | create session | 清除 challenge，重新获取 | consumed/locked/superseded 使用同一类别 |
| `CHALLENGE_EXPIRED` | 410 | create session | 清除 challenge，重新获取 | 服务端时钟为权威 |
| `UNAUTHENTICATED` | 401 | get session/protected | 清除 UI 摘要并转登录 | missing/expired/revoked/account-disabled 不细分 |
| `DELIVERY_UNAVAILABLE` | 503 | challenge | 中性暂时失败，保留 request_id | 只表示 provider-wide unavailable；所有账户类别一致 |
| `SERVICE_UNAVAILABLE` | 503 | all | 保持 fail-closed，允许用户稍后重试 | DB/Redis/key configuration 无法确认 |
| `INTERNAL_ERROR` | 500 | all | 中性失败并记录 request_id | 无内部异常或敏感材料 |

## Request challenge anti-enumeration

对格式合法的 active、unknown、suspended、deleted 手机号：

- provider health 正常时均返回 HTTP 202、`code="0"`、同一 message 类别和
  `ChallengeAcceptedData` shape；
- 202 在 pending challenge 与幂等结果提交后、recipient-specific dispatcher send 前返回；
- `challenge_id` 是 opaque handle，不证明账户存在；
- `phone_masked` 只由请求者刚输入的值派生；
- 不返回 `ACCOUNT_UNAVAILABLE`、`PHONE_NOT_FOUND` 或 delivery recipient detail；
- provider-wide outage 在账户分支之前确定，并对全部类别返回同一
  `DELIVERY_UNAVAILABLE`。
- dispatcher 后续形成的 accepted/rejected/timeout/unknown 只更新内部 challenge 状态，
  不改变或补发浏览器公开结果，也不得被 UI 解释为“短信已发送”。

## Verification action mapping

| Server condition | Public code | `data.action` | Attempts |
|------------------|-------------|---------------|----------|
| format-valid wrong code, attempts remain | `VERIFICATION_FAILED` | `retry_code` | increment |
| fifth wrong code | `VERIFICATION_FAILED` | `request_new_code` | lock at 5 |
| decoy / ineligible challenge | `VERIFICATION_FAILED` | `retry_code` then `request_new_code` | same external lifecycle |
| expired | `CHALLENGE_EXPIRED` | n/a | no additional increment |
| consumed/locked/superseded | `CHALLENGE_UNAVAILABLE` | n/a | no additional increment |
| malformed code | `VALIDATION_ERROR` | n/a | no increment |

不得在错误 data 中返回 code digest、完整手机号、账户状态、session id 或 provider detail。

## Session and logout

- Create session success sets `__Host-tokenmarket_session` but response body never contains it。
- `GET /session` 401 使用统一 `UNAUTHENTICATED` 并清除无效 Cookie。
- `DELETE /session` 对 missing/already-revoked Cookie 返回幂等 `0`；若 Cookie 当前有效，
  缺少或错误 CSRF/Origin 返回 `CSRF_INVALID` / `ORIGIN_REJECTED` 且不撤销。
- 旧设备 logout 只按旧 token digest 操作，不能撤销后来签发的新 session。

## Logging and telemetry

允许：business code、HTTP status、duration、request_id、低基数 outcome。

禁止：Cookie/Set-Cookie、CSRF、OTP、原幂等键、完整手机号、原 IP、challenge/session token。
