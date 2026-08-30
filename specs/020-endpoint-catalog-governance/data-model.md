# Data Model：V0.2 契约与端点目录治理

本功能无数据库表。事实源为已提交契约文件。以下为机器目录与领域契约的逻辑模型。

## EndpointCatalog

| 字段 | 约束 |
|------|------|
| `schema_version` | 契约文件格式版本，本发布 `1.0.0` |
| `catalog_major` | 整数 ≥1；与消费者声明比较 |
| `catalog_minor` | 整数 ≥0；兼容增补 |
| `freeze_date` | `YYYY-MM-DD`，本发布 `2026-08-31` |
| `providers` | 恰好 `openai`、`anthropic`、`vertex` |
| `records` | 非空数组 |

**不变量**：加载后只读快照；主版本比较失败则整个对象不可用。

## EndpointRecord

| 字段 | 约束 |
|------|------|
| `id` | 稳定 slug，目录内唯一 |
| `provider` | `openai` \| `anthropic` \| `vertex` |
| `protocol_version` | 非空，如 `v1`、`vertex-v1` |
| `method` | `GET` \| `POST` \| `PUT` \| `PATCH` \| `DELETE` \| `WEBSOCKET` |
| `path_template` | 以 `/` 开头的规范模板 |
| `stability` | `stable` \| `preview` \| `beta` \| `control_plane` |
| `capability_tags` | 字符串数组，可空但不缺字段 |
| `stateful` | boolean |
| `transport` | `http` \| `sse` \| `websocket` \| `multipart` \| `binary` |
| `affinity` | `none` \| `connection` \| `resource_id` |
| `metering_source` | `usage` \| `reported_cost` \| `mixed` \| `unresolved` \| `none` |
| `first_supported_version` | 非空，本发布多为 `v0.2.0` |
| `test_fixture_version` | 非空 |
| `official_source` | 非空 URL 或文档标识 |
| `owning_sf` | 如 `SF19` |
| `requires_project_opt_in` | boolean；preview/beta 必须为 true |

**唯一键**：`(provider, protocol_version, method, path_template)`。

**匹配规则**：规范化 method 大写；path 去掉查询串；按模板变量段匹配；多匹配时取
模板静态字符最长者；仍冲突则校验阶段已失败（发布目录不得含歧义对）。

## CatalogAdmissionInput / Decision

输入：provider、method、path、`project_mode`（`shared`\|`dedicated`\|`unknown`）、
`preview_opt_in`（bool）。

输出：`allow` 或错误码之一：

- `ENDPOINT_NOT_CATALOGED`
- `CONTROL_PLANE_NOT_ALLOWED`
- `PREVIEW_NOT_ENABLED`
- `DEDICATED_PROJECT_REQUIRED`

`unknown` 模式对 `stateful=true` 视为共享（失败关闭，不得猜测专享）。

## 领域契约实体（仅 schema，无持久化）

### Project

- `project_id`、`owner_account_id`、`mode`（创建后不可变）、`enabled_protocols[]`
- 禁止 schema 提供 `PATCH mode`

### ProviderConnection

- `connection_id`、`seller_account_id`、`provider`、`mode`
- `credential_ref` write-only；响应仅 `credential_fingerprint`
- 无 `credential_plaintext` 读字段

### RouteDecision

- `decision_id`、`request_id`、`catalog_major`、`scoring_version`
- `hard_filter_exclusions[]`、`candidates[]`、`selected_connection_id`
- `explain` 可重放；`self_trade_excluded` 恒为事实

### UsageObservation

- 多维 token/usage 整数；可选 `reported_cost_minor_units` + `currency`
- `cost_status`: `reported` \| `rated` \| `unresolved`；禁止用 0 表示未知

### Pricing

- `rate_version`、`buyer_multiplier`、`seller_quote_multiplier`、上下界
- 定点小数以整数 minor units + `scale` 表示

### LedgerEntry

- `entry_id`、`account_id`、`amount_minor_units`、`direction`
- 仅 `append`；无 update/delete 操作形状
- `status`: `reserved` \| `settled` \| `released` \| `unresolved` \| `reversed`

### AuditEvent

- 事件信封：`event_id`、`type`、`version`、`timestamp`、`payload`、`producer`、`correlation_id`
- 用于目录发布、高风险配置；payload 脱敏

## 状态与生命周期

目录记录本身无运行时状态机。准入是纯函数。领域实体状态机由后续 SF 实现，但
契约必须已经禁止非法迁移（例如 Project mode 变更、账本改写、凭据回读）。
