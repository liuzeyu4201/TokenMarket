# 管理员 RBAC

| 动作 | support | supply_ops | pricing | ledger | security_audit |
|------|---------|------------|---------|--------|----------------|
| user.lookup | 读写/只读 | 否 | 否 | 否 | 只读 |
| user.force_logout | 写 | 否 | 否 | 否 | 写 |
| connection.view_health | 否 | 读写/只读 | 否 | 否 | 只读 |
| connection.replace_dedicated | 否 | 写 | 否 | 否 | 否 |
| price.publish | 否 | 否 | 写 | 否 | 否 |
| route.rollback | 否 | 否 | 写 | 否 | 否 |
| ledger.reverse | 否 | 否 | 否 | 写 | 否 |
| ledger.edit_balance | 否 | 否 | 否 | 否 | 否 |
| credential.read | 否 | 否 | 否 | 否 | 否 |
| audit.read | 只读 | 否 | 否 | 否 | 读写/只读 |
| audit.delete | 否 | 否 | 否 | 否 | 否 |
| break_glass | 否 | 否 | 否 | 否 | 写 |

只读角色仅允许表中“只读/读写”的读动作。
