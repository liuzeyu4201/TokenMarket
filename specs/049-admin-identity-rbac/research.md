# Phase 0 Research

## Decision 1：独立 Cookie

用户 `__Host-tokenmarket_session`；管理员 `__Host-tokenmarket_admin_session` 且 Path=`/admin`。互认失败关闭。

## Decision 2：RBAC 矩阵

角色 `support` `supply_ops` `pricing` `ledger` `security_audit`，可标记 readonly。`credential.read` 与 `ledger.edit_balance` 与 `audit.delete` 永不允许。

## Decision 3：审计哈希链

每条记录 `record_hash = sha256(prev_hash || canonical_json)`。mutate/delete 抛 `IMMUTABLE_AUDIT`。
