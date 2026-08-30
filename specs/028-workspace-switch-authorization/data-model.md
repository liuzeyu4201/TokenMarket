# Data Model：会话工作区

## AuthSession（扩展）

| 字段 | 约束 |
|------|------|
| workspace | VARCHAR(8) NOT NULL；`buyer` 或 `seller` |

登录时按账户角色默认赋值。seller 角色回填 `seller`，其余 `buyer`。

不变量：`role=buyer ⇒ workspace=buyer`；`role=seller ⇒ workspace=seller`；`role=both ⇒ workspace ∈ {buyer,seller}`。

## WorkspaceSwitchAudit

沿用 `authentication_security_events`：`workspace_switched` / `workspace_switch_denied`。
