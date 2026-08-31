# admin-identity v1

Version: 1.0.0（SF30 管理员身份与 RBAC）

- Cookie：`__Host-tokenmarket_admin_session`，Path=`/admin`，与用户 `__Host-tokenmarket_session` 分离。
- 路由前缀：`/admin/v1`。
- 角色：`support` `supply_ops` `pricing` `ledger` `security_audit`，可只读。
- 永不允许：`credential.read` `ledger.edit_balance` `audit.delete`。
- 高风险：价格发布、路由回滚、专享更换、会话强退、冲正、break-glass；需 MFA、近期 step-up、原因。
