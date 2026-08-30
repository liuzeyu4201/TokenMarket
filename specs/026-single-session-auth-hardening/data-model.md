# Data Model：单会话世代

## User（扩展）

| 字段 | 约束 |
|------|------|
| session_generation | INTEGER NOT NULL DEFAULT 1；仅登录成功与全部退出时 +1 |

## AuthSession（扩展）

| 字段 | 约束 |
|------|------|
| session_generation | INTEGER NOT NULL；签发时复制账户世代 |
| client_hint | VARCHAR(32) NULL；IP/UA HMAC 截断，供安全页展示 |

不变量：有效会话 ⇒ `revoked_at IS NULL` 且 `session_generation = users.session_generation`。

## AuthSecurityEvent

沿用既有表。新增/确保 `session_replaced`、`session_revoked_all` 事件类型可查询。无 token。
