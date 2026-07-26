# 契约：注册业务码（v1）

**所有者**：API Service
**信封**：见 OpenAPI `ApiEnvelope`
**版本**：1.0.0

全部注册响应使用统一信封。客户端**必须**根据 `code`（字符串）分支，而非仅看 HTTP 状态。

| code | HTTP（典型） | 含义 | 是否创建用户？ |
|------|----------------|---------|---------------|
| `0` | 200 | 成功（创建，或 24h 内幂等重放） | 仅首次成功时 |
| `VALIDATION_ERROR` | 400 | 字段/格式错误；`data.errors` 为 field → messages | 否 |
| `PHONE_ALREADY_REGISTERED` | 409 | 活跃账户占用该手机号 | 否 |
| `ACCOUNT_UNAVAILABLE` | 409 | 软删除（或其他不可再创建）账户占用手机号；恢复不在范围内 | 否 |
| `IDEMPOTENCY_KEY_CONFLICT` | 409 | 同一 key、不同请求哈希 | 否 |
| `IDEMPOTENCY_KEY_EXPIRED` | 409 | key 超过 24h；客户端必须使用新 key | 否 |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | 缺失/非法幂等 key | 否 |
| `RATE_LIMITED` | 429 | IP 或手机号维度超限 | 否 |
| `SERVICE_UNAVAILABLE` | 503 | DB 或限流后端不可用；若创建可能已提交，可安全用**同一** key 重试 | 否* |
| `INTERNAL_ERROR` | 500 | 意外错误；若事务已回滚则无部分用户 | 否 |

\*若客户端不确定提交是否成功，在 24h 内用**同一**幂等 key 重试。

## 消息隐私规则

- 不得包含其他用户的昵称、角色、状态或完整手机号。
- `PHONE_ALREADY_REGISTERED` 与 `ACCOUNT_UNAVAILABLE` 在 **code** 与用户可见类别上保持区分，但均不泄露账户资料字段。
- 可选 `data.phone_masked` 仅用于调用方自身成功路径（例如 `*******8000`）。

## 字段错误形状（`VALIDATION_ERROR`）

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
