# Contract：Authorization Matrix v1

**Owner**: API Service authorization domain  
**policy_version**: `authz-matrix-v1`  
**Default**: deny

## Actions

| Action | Resource type | Resource id required | Notes |
|--------|---------------|----------------------|-------|
| `proxy_key.create` | `proxy_key` | no (created as owner=self) | 创建后所有权归当前用户 |
| `proxy_key.revoke` | `proxy_key` | yes | 需所有权；生命周期 → **`disabled`**（V0.1 钉死；非 soft_deleted） |
| `proxy_key.use` | `proxy_key` | yes | 需所有权且 `active`；高频允许不写逐条审计 |
| `seller_key.register` | `seller_key` | no | 接入后所有权归当前用户 |
| `seller_key.read` | `seller_key` | yes | 需所有权；`disabled` 可读，`soft_deleted` → not_found |
| `seller_key.update` | `seller_key` | yes | 需所有权且非 soft_deleted |
| `seller_key.disable` | `seller_key` | yes | 需所有权 |
| `route_candidate_exclude_self` | n/a | no | 输入候选列表；输出过滤列表 |
| `project.create` | `project` | no | 买家工作区；创建时选择不可变 mode |
| `project.read` | `project` | yes | 仅所有者；他账号与缺失同形 404 |
| `project.update` | `project` | yes | 重命名等；不得改 mode |
| `project.archive` | `project` | yes | 归档后禁止新代理请求 |
| `project.delete` | `project` | yes | 有阻塞项则拒绝 |
| `project.enable_protocol` | `project` | yes | 创建后启用须 Binding |

## Role matrix

| Action | buyer | seller | both |
|--------|:-----:|:------:|:----:|
| `proxy_key.create` | allow | deny | allow |
| `proxy_key.revoke` | allow | deny | allow |
| `proxy_key.use` | allow | deny | allow |
| `seller_key.register` | deny | allow | allow |
| `seller_key.read` | deny | allow | allow |
| `seller_key.update` | deny | allow | allow |
| `seller_key.disable` | deny | allow | allow |
| `route_candidate_exclude_self` | allow | deny | allow |
| `project.create` | allow | deny | allow |
| `project.read` | allow | deny | allow |
| `project.update` | allow | deny | allow |
| `project.archive` | allow | deny | allow |
| `project.delete` | allow | deny | allow |
| `project.enable_protocol` | allow | deny | allow |

`allow` 仍须通过账户 eligible 与（若适用）所有权/生命周期检查。

## Self-route exclusion

```text
filtered = [ c in candidates
             where c.owner_user_id != buyer_user_id
               and c.lifecycle_status == active ]
```

- 不得在 `filtered` 为空时把本人 Key 加回。  
- 输入中本人 Key 的存在不得影响对外错误细节（统一 `NO_ROUTE_CANDIDATE`）。  
- 所有权变更后新请求必须在 ≤1s 内使用新所有权（直读或可靠失效）。

## Evaluation order

1. Authenticated `user_id` from session only  
2. Load user facts → eligible?  
3. Matrix `(role, action)`  
4. Ownership / lifecycle if resource-bound  
5. Self-route filter if routing action  
6. Metrics；conditional audit  

## Client-supplied identity fields

请求中的 `user_id`、`buyer_id`、`seller_id`、`role`、`owner_user_id` **MUST be ignored**
for authorization identity and role. Ownership assignment on create **MUST** use session
user id only.
