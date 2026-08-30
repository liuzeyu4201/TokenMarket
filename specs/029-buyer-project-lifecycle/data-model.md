# Data Model：买家 Project

## 状态机

```text
create → draft
draft --activate--> active
draft --archive--> archived
active --suspend--> suspended
active --archive--> archived
suspended --activate--> active
suspended --archive--> archived
archived → （仅查询；无依赖时可逻辑删除）
```

非法边：409 `ILLEGAL_STATE_TRANSITION`，行不变。

逻辑删除：`deleted_at` 非空。之后 GET/PATCH/状态/协议均同形 404。列表不含已删除。归档仍可 GET/列表。

## Project

| 字段 | 约束 |
|------|------|
| id | UUID PK，不可猜测 |
| owner_account_id | UUID NOT NULL FK users.id |
| display_name | VARCHAR(128) NOT NULL |
| name_normalized | VARCHAR(128) NOT NULL = lower(btrim(display_name)) |
| mode | `shared` \| `dedicated` NOT NULL；更新触发器禁止变更 |
| status | `draft` \| `active` \| `suspended` \| `archived` NOT NULL |
| created_at / updated_at | timestamptz |
| archived_at | timestamptz NULL |
| deleted_at | timestamptz NULL |

唯一：`(owner_account_id, name_normalized) WHERE deleted_at IS NULL`。

不变量：mode 创建后恒定；协议集合共享该 mode。

## ProjectProtocol

| 字段 | 约束 |
|------|------|
| project_id | UUID FK projects.id |
| protocol | `openai` \| `anthropic` \| `vertex` |
| enabled | BOOLEAN NOT NULL |
| enabled_at / disabled_at | timestamptz |

PK `(project_id, protocol)`。停用不删行。

## DeletionBlocker（`project_runtime_blockers`）

| 字段 | 约束 |
|------|------|
| id | UUID PK |
| project_id | UUID FK |
| kind | `key` \| `in_flight_task` \| `unsettled_ledger` |
| reference_id | VARCHAR(128) |
| created_at | timestamptz |
| resolved_at | timestamptz NULL（NULL=仍阻塞） |

## ProjectAdmission

非持久化视图：`allows_new_proxy = (deleted_at IS NULL AND status = 'active')`。

## Idempotency / Audit

- `project_idempotency`：`(owner_account_id, idempotency_key)` → request_hash + project_id
- `project_audit_events`：event_type、owner、project_id、request_id、payload JSONB（无秘密）

## Binding 端口（非表）

`BindingLookup.has_enabled_binding(owner_id, project_id, protocol) -> bool`。本 SF `EmptyBindingLookup` → False。
