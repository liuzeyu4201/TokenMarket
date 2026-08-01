# Runbook：角色授权与自买自卖隔离（SF05）

**Owner**: API Service  
**Related metrics**: `tokenmarket_authz_*`

## Symptoms

- 授权相关请求大量 `SERVICE_UNAVAILABLE` (503)
- 角色变更后仍可使用旧权限
- 审计事件无法按 `request_id` 查询
- 非生产夹具在生产环境可访问

## Triage

1. **DB 可用性**: 检查 API Service readiness / PostgreSQL。事实源不可达必须 fail-closed（拒绝，非允许）。
2. **审计落盘失败**: 拒绝路径要求先写入 `authorization_security_events`（或 pending outbox）。若落盘失败，客户端应得 503，**不应**收到无证据的 403/404。
3. **夹具误开**: 确认 `AUTHORIZATION_FIXTURES_ENABLED` 在 prod 为 false/unset；`APP_ENV`/`MODE` 为 prod。
4. **角色未生效**: 授权读取 `users` 当前角色，不使用会话 `role_snapshot`。确认用户行已更新且无陈旧副本（V0.1 无加速层）。

## Recovery

- 恢复 PostgreSQL 连接与磁盘。
- 出站 outbox（若启用 worker）积压：检查 `authorization_audit_outbox` 中 `state=pending` 行年龄。
- 误开夹具：关闭配置并滚动重启 API；审计是否被滥用。

## Notes

- 日志/指标禁止完整手机号、Cookie、原始 Key。
- 回滚：停用 authorization 路由或回退镜像；保留审计表。
