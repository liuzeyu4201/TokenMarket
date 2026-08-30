# Data Model：Provider Binding

## 状态机

```text
create → draft
draft --validate--> validated
draft|validated --publish--> active   （同协议原 active → inactive）
active --deactivate--> inactive
active --connection_invalid--> degraded
degraded --deactivate--> inactive
```

已发布（active/inactive/degraded）配置列不可变。

## ProviderBinding

| 字段 | 约束 |
|------|------|
| id | UUID PK |
| project_id | UUID FK projects.id |
| owner_account_id | UUID |
| protocol | openai \| anthropic \| vertex |
| supply_mode | shared \| dedicated，必须等于 Project.mode |
| status | draft \| validated \| active \| inactive \| degraded |
| version | INT ≥1，同一 project+protocol 发布时递增 |
| allowed_providers | TEXT[] ；必须 ⊆ {protocol} |
| allowed_models | TEXT[] ；shared 至少 1 个 |
| allowed_regions | TEXT[] 可选 |
| connection_id | UUID NULL；dedicated NOT NULL |
| published_at | timestamptz NULL |
| created_at / updated_at | timestamptz |

部分唯一：`(project_id, protocol) WHERE status = 'active'`。

## BindingAdmission

非持久化：`admit(project, protocol, provider, model)` → 锁定的 version 快照或拒绝。degraded → 失败，无共享候选。

## SdkHint

`base_url`、`auth_scheme`、`protocol_version`。无 secret。

## ConnectionFact（端口）

connection_id、supply_mode=dedicated、provider、usable: bool。
