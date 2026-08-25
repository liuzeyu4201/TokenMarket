# Proxy Gateway

TokenMarket Go ingress gateway (SF01 scaffold + SF06 火山方舟凭证验证).

## Ownership

- Owner: TokenMarket Engineering
- Type: Go service
- Responsibilities: operational health/metrics, **internal** provider credential validation
  (Volcano Ark), future: authentication, rate limiting, routing, forwarding, metering

## SF06 — 火山方舟凭证与额度验证

契约：`shared/contracts/volcano-key-validation/v1/`

### 行为摘要

- 领域 API：`application.ValidateCredential`（无状态、3s 硬截止）
- 上游探活：`GET {VOLCANO_VALIDATE_BASE_URL}/models`
- V0.1 默认额度：`NoopQuotaReader` → `error_category=quota_unavailable`（**禁止**假 0）
- 内部 HTTP（可选）：`POST /internal/v1/provider-credentials/validate`
  - 需 `PROVIDER_VALIDATE_INTERNAL_ENABLED=true` + `X-Internal-Token`
  - 非 `volcano` 的 `platform` → HTTP **200** + `unsupported_platform`（非 422）
  - 宪章 II / C1：静态 token **不足**公网唯一防护
  - **local/dev**：可将 validate 挂在主 listener（开发便利）
  - **test/prod**（`MustIsolateInternalListener`）：validate **不**挂公网 `:PORT`；
    独立回环 listener `PROVIDER_VALIDATE_BIND`（默认 `127.0.0.1`）+
    端口 `PROVIDER_VALIDATE_INTERNAL_PORT`（默认与 `PORT` 相同，即 `127.0.0.1:PORT`）
  - 配置 fail-closed：非 local 启用且 bind 非回环且未 `ALLOW_NON_LOOPBACK` → 启动失败

### 本地示例

```bash
export APP_ENV=local
export PROVIDER_VALIDATE_INTERNAL_ENABLED=true
export PROVIDER_VALIDATE_INTERNAL_TOKEN=local-dev-only-token
export PROVIDER_VALIDATE_BIND=127.0.0.1
export VOLCANO_V01_CHAT_MODELS=doubao-pro-32k,doubao-lite-32k
# 指向 mock 上游，勿默认打真实火山
export VOLCANO_VALIDATE_BASE_URL=http://127.0.0.1:18080/api/v3
go run ./cmd/gateway
```

## Commands

```bash
make bootstrap
make fmt
make type-check
make lint
make test
make build
```

```bash
go test ./... -count=1
go test ./internal/domain/providervalid/ ./internal/infrastructure/platform/volcano/ -cover
```

## SF07 — 火山方舟请求与响应兼容

契约：`shared/contracts/volcano-openai-compat/v1/`

V0.1 公开入口：`POST /v1/proxy/volcano/chat/completions`（SF12/SF15）。
适配仍为同进程 `ChatService.Complete` / `OpenStream`；`PROXY_ENABLED=0` 可关闭挂载。

- 出站：`POST {VOLCANO_CHAT_BASE_URL}/chat/completions`（默认复用 `VOLCANO_VALIDATE_BASE_URL`）
- 允许列表：`model`/`messages`/`stream`/`temperature`/`max_tokens`/`top_p`/`stop`/penalty/`n=1`
- `messages[].content` 原样转发；`usage` 缺失 **禁止**填 0
- 缺截止默认 60s；**生成请求禁止自动重试**

```bash
export VOLCANO_V01_CHAT_MODELS=doubao-pro-32k,doubao-lite-32k
export VOLCANO_CHAT_BASE_URL=http://127.0.0.1:18080/api/v3
go test ./internal/domain/chatcompat/ ./internal/application/ ./internal/infrastructure/platform/volcano/ -count=1
```
