# 平台目录错误码（SF01）

数据面在**目录判定阶段**只允许下列稳定业务错误（统一信封 `code` 字段）。
这些错误与上游原生错误可区分；本阶段不得伪造上游响应。

| code | 何时 | HTTP 建议 |
|------|------|-----------|
| `ENDPOINT_NOT_CATALOGED` | method/path 无目录记录 | 404 |
| `CONTROL_PLANE_NOT_ALLOWED` | 命中 `stability=control_plane` | 403 |
| `PREVIEW_NOT_ENABLED` | 命中 preview/beta 且 Project 未 opt-in | 403 |
| `DEDICATED_PROJECT_REQUIRED` | `stateful=true` 且 Project 不是 dedicated | 403 |
| `CATALOG_VERSION_MISMATCH` | 进程声明的主版本 ≠ 目录 `catalog_major` | 启动失败，不服务 |
| `CATALOG_LOAD_FAILED` | 文件缺失、JSON 非法或完整性校验失败 | 启动失败，不服务 |

兼容：已发布错误码不得改含义。新增码必须次版本说明；删除码必须主版本。
