# Implementation Plan: 原生同协议透明代理核心

**Branch**: `035-native-passthrough-kernel` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

在 proxy-gateway 新增 `passthrough` 内核：目录准入、协议解析、字节流 ReverseProxy、header 契约剥离、平台信封与 upstream 原生错误分离。不调用 chatcompat。Volcano 适配器路径保持独立。

## Technical Context

**Language/Version**: Go 1.25.14

**Primary Dependencies**: endpcatalog.Admit、net/http/httputil.ReverseProxy、既有平台信封

**Storage**: N/A

**Testing**: Go testing + race；golden body；取消；源码无转换

**Affected Components**: `services/proxy-gateway/internal/domain/passthrough/`、`httpserver`、`shared/contracts/native-passthrough/v1/`

**Contracts**: `native-passthrough/v1` 1.0.0 新建（header 政策 + 错误码）

**Security**: 剥离 hop-by-hop/Cookie/内部头；upstream 凭证不回传到客户端

## Constitution Check

### Pre-Research Gate: PASS

契约先行；内核在 gateway 域内；不新增服务；测试先行。

### Post-Design Gate: PASS

不引入跨协议适配器；Selector 为端口而非新进程。不付费调用。

## Complexity Tracking

无宪章违规。ReverseProxy 用于保字节与流语义，不构成新服务。
