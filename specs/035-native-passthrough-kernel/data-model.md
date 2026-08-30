# Data Model：透传内核（无持久化）

## ResolvedRequest

| 字段 | 含义 |
|------|------|
| Protocol | openai \| anthropic \| vertex |
| Path | 去掉协议前缀后的目录路径 |
| Endpoint | 目录记录（只读） |

## Upstream

BaseURL、Credential（进程内，不入日志）、AuthHeader（Authorization 或 x-api-key）。

## PlatformError

code：PROTOCOL_UNRESOLVED、ENDPOINT_NOT_CATALOGED、CONTROL_PLANE_NOT_ALLOWED、PREVIEW_NOT_ENABLED、DEDICATED_PROJECT_REQUIRED、REQUEST_TOO_LARGE、UPSTREAM_TIMEOUT、CLIENT_CANCELED、NO_UPSTREAM。

无表、无迁移。
