# Contract: Registration Business Codes (v1)

**Owner**: API Service  
**Envelope**: See OpenAPI `ApiEnvelope`  
**Version**: 1.0.0

All registration responses use the unified envelope. Clients **must** branch on `code` (string), not only HTTP status.

| code | HTTP (typical) | Meaning | Creates user? |
|------|----------------|---------|---------------|
| `0` | 200 | Success (create or idempotent replay within 24h) | Only on first success |
| `VALIDATION_ERROR` | 400 | Field/format errors; `data.errors` maps field → messages | No |
| `PHONE_ALREADY_REGISTERED` | 409 | Active account holds phone | No |
| `ACCOUNT_UNAVAILABLE` | 409 | Soft-deleted (or otherwise non-recreatable) account holds phone; recovery out of scope | No |
| `IDEMPOTENCY_KEY_CONFLICT` | 409 | Same key, different request hash | No |
| `IDEMPOTENCY_KEY_EXPIRED` | 409 | Key older than 24h; client must use a new key | No |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | Missing/invalid idempotency key | No |
| `RATE_LIMITED` | 429 | IP or phone dimension exceeded | No |
| `SERVICE_UNAVAILABLE` | 503 | DB or rate-limit backend unavailable; safe to retry with **same** key if create may have committed | No* |
| `INTERNAL_ERROR` | 500 | Unexpected; no partial user if transaction rolled back | No |

\*If the client is unsure whether commit succeeded, retry with the **same** idempotency key within 24h.

## Privacy rules for messages

- Must not include other users' nickname, role, status, or full phone.
- `PHONE_ALREADY_REGISTERED` and `ACCOUNT_UNAVAILABLE` messages stay distinct in **code** and user-visible category, but neither reveals account profile fields.
- Optional `data.phone_masked` only for the caller's own success path (e.g. `*******8000`).

## Field errors shape (`VALIDATION_ERROR`)

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求参数不合法",
  "data": {
    "errors": {
      "phone": ["手机号格式不正确"],
      "nickname": ["昵称长度须为 1–50 个字符"],
      "role": ["角色必须是 buyer、seller 或 both"]
    }
  },
  "request_id": "...",
  "timestamp": "..."
}
```
