# Phase 0 Research：流与亲和

## Decision 1：扩展 native-passthrough 1.1.0

**Decision**: 不新建 catalog 目录。增加 affinity/transport 错误码与政策。

## Decision 2：亲和表独立包

**Decision**: `internal/domain/affinity`：Put/Get；冲突 fail-closed。Memory + 可选 JSON 快照文件（非明文 body）。

## Decision 3：SSE 用 ReverseProxy FlushInterval + write deadline

**Decision**: 不解析 event 名。Idle 通过 ResponseController/写超时。慢客户端超时结束该流。

## Decision 4：WS 允许 Upgrade 仅当 catalog transport=websocket

**Decision**: 其它端点仍剥离 Upgrade。101 后字节复制。

## Decision 5：创建响应登记 id

**Decision**: Tee 响应前 64KiB JSON 顶层 `id`（及常见 `*_id`），不改变后续字节流。
