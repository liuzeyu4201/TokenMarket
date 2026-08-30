# Implementation Plan: 代理网关无状态化与水平扩展

**Branch**: `021-gateway-stateless-scale` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 proxy-gateway 引入不可变 `RuntimeSnapshot`（含 SF01 目录）、原子切换与请求级 Pin；
Drain 摘流；本地用量 WAL 降为可丢弃缓存，启动不依赖本地文件。不实现 Redis 占用（SF03）
与 Outbox（SF04）。

## Technical Context

**Language/Version**: Go 1.25.14  
**Primary Dependencies**: 标准库 `sync/atomic`、既有 gin server、endpcatalog  
**Storage**: N/A（禁止新的节点私有事实源）  
**Testing**: Go testing + race；并发切换；Drain httptest  
**Affected Components**: `services/proxy-gateway/internal/domain/runtimesnap/`、`httpserver`、`usageobs`、`cmd/gateway`

## Constitution Check

### Pre-Research Gate: PASS

Gateway 领域包拥有快照；不跨服务读库；无新服务。测试先于实现。

### Post-Design Gate: PASS

快照/Drain 契约在测试中定义；用量 WAL 不再是 SoR；脱敏保持。

## Project Structure

```text
services/proxy-gateway/internal/domain/runtimesnap/
services/proxy-gateway/internal/httpserver/  # drain + readiness
services/proxy-gateway/internal/domain/usageobs/
```

## Complexity Tracking

无宪章违规。
