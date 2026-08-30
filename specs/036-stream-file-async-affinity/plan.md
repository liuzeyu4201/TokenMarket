# Implementation Plan: SSE、WebSocket、文件与异步资源亲和

**Branch**: `036-stream-file-async-affinity` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

扩展透传内核：SSE 流式 flush + idle；WebSocket 保留 Upgrade；multipart 限大小不落盘；resource_id 亲和表 fail-closed 钉住 Connection。扩展 `native-passthrough/v1` 1.1.0。

## Technical Context

**Language/Version**: Go 1.25.14

**Primary Dependencies**: passthrough Kernel、endpcatalog Admit、usageoutbox 幂等

**Storage**: 进程内亲和表 + 可选文件快照（重启）；无明文临时上传文件

**Testing**: Go testing+race；SSE 顺序；WS 101；上传截断；亲和缺失；短时并发 soak

**Contracts**: `native-passthrough/v1` 1.1.0 expand-only

## Constitution Check

### Pre-Research Gate: PASS

契约先行；不新增服务；测试先行。

### Post-Design Gate: PASS

不引入跨协议转换；不落盘明文；全量 2h soak 为可启用夹具而非跳过亲和测试。

## Complexity Tracking

无宪章违规。
