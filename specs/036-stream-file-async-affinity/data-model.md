# Data Model：资源亲和

## AffinityBinding

| 字段 | 约束 |
|------|------|
| protocol | openai \| anthropic \| vertex |
| resource_id | 厂商资源 ID |
| connection_id | 创建时 Connection |
| project_id | 可选 |
| endpoint_id | 目录 ID |

主键 (protocol, resource_id)。已存在且 connection_id 不同 → AFFINITY_CONFLICT。缺失 → AFFINITY_NOT_FOUND。

无上传明文临时表。
