# Contract：Role Access Isolation Business Codes v1

**Owner**: API Service authorization domain  
**Envelope**: `{code, message, data, request_id, timestamp}`  
**OpenAPI**: [role-access-isolation.openapi.yaml](./role-access-isolation.openapi.yaml)

客户端与后续服务必须以稳定 `code` 分支，不得仅依赖 HTTP status 文案。

## Codes

| Code | HTTP | When | Client action | Security semantics |
|------|------|------|---------------|--------------------|
| `0` | 200 | 夹具/评估允许成功 | 读 data | 不表示生产 Key 已签发 |
| `UNAUTHENTICATED` | 401 | 无会话、过期、已撤销 | 重新登录 | 不区分原因细节 |
| `FORBIDDEN_ROLE` | 403 | 角色矩阵拒绝该 action | 停止；提示权限不足 | 不泄露目标资源是否存在 |
| `ACCOUNT_UNAVAILABLE` | 403 | suspended / soft / 非 active | 停止；中性不可用 | 不区分 suspended vs deleted |
| `RESOURCE_NOT_FOUND` | 404 | 不存在、soft_deleted、非所有者 | 视为无此资源 | **三者同码同 HTTP** |
| `NO_ROUTE_CANDIDATE` | 404 | 自排除后候选为空 | 无可路由资源；稍后/换条件 | 不暗示本人是否持有 Key |
| `VALIDATION_ERROR` | 400 | action/资源类型/UUID 非法 | 修复请求 | 无状态变化 |
| `SERVICE_UNAVAILABLE` | 503 | 事实源不可达，或拒绝路径上审计事件/pending 意图无法在响应前落盘 | 重试 | fail-closed；禁止无证据的业务 403/404 |
| `INTERNAL_ERROR` | 500 | 未分类故障 | 带 request_id 报障 | 无堆栈/密钥 |

## 映射规则

| 内部 reason_code（审计） | 对外 code |
|--------------------------|-----------|
| `UNAUTHENTICATED` | `UNAUTHENTICATED` |
| `ROLE_DENIED` | `FORBIDDEN_ROLE` |
| `ACCOUNT_SUSPENDED` / `ACCOUNT_DELETED` / `ACCOUNT_INACTIVE` | `ACCOUNT_UNAVAILABLE` |
| `NOT_OWNER` / `RESOURCE_MISSING` / `RESOURCE_SOFT_DELETED` | `RESOURCE_NOT_FOUND` |
| `SELF_ROUTE_EMPTY` | `NO_ROUTE_CANDIDATE` |
| `FACT_STORE_UNAVAILABLE` / `AUDIT_PERSIST_FAILED` | `SERVICE_UNAVAILABLE` |

## 日志与遥测允许/禁止

**允许**：`code`、HTTP status、`action`、`policy_version`、`reason_code`（低基数）、
`request_id`、耗时、候选数量与过滤数量、结果计数器。

**禁止**：Cookie、session token、CSRF、原始 Key、完整代理 Key、完整手机号、未脱敏
Authorization 头、其他用户 PII。

## 批量

V0.1 **无**批量授权 API（spec FR-011，范围外）。若未来接口引入批量敏感操作：默认全有或全无；任一资源授权失败 → 整体失败，采用该失败的对外 code；不返回部分成功列表，除非该接口契约显式支持部分成功。
