# SF01 契约源

本目录为评审源。实现时字节物化到 `shared/contracts/`：

| 源文件 | 物化路径 |
|--------|----------|
| `catalog.schema.json` | `shared/contracts/endpoint-catalog/v1/catalog.schema.json` |
| `catalog.json` | `shared/contracts/endpoint-catalog/v1/catalog.json` |
| `CATALOG.md` | `shared/contracts/endpoint-catalog/v1/CATALOG.md` |
| `freeze-record.md` | `shared/contracts/endpoint-catalog/v1/freeze-record.md` |
| `platform-errors.md` | `shared/contracts/endpoint-catalog/v1/platform-errors.md` |
| `compatibility.md` | `shared/contracts/endpoint-catalog/v1/compatibility.md` |
| `project.openapi.yaml` | `shared/contracts/project/v1/project.openapi.yaml` |
| `provider-connection.openapi.yaml` | `shared/contracts/provider-connection/v1/provider-connection.openapi.yaml` |
| `route-decision.schema.json` | `shared/contracts/route-decision/v1/route-decision.schema.json` |
| `usage-observation.schema.json` | `shared/contracts/usage/v1/usage-observation.schema.json` |
| `pricing.schema.json` | `shared/contracts/pricing/v1/pricing.schema.json` |
| `ledger-entry.schema.json` | `shared/contracts/ledger/v1/ledger-entry.schema.json` |
| `audit-event.schema.json` | `shared/contracts/audit/v1/audit-event.schema.json` |

`catalog.json` 与 `CATALOG.md` 由实现生成并提交；测试锁定二次生成无差异。
