# Proxy Gateway

TokenMarket Go 数据面入口：V0.2 原生同协议透传（OpenAI / Anthropic / Vertex），保留 V0.1 火山 OpenAI 兼容 Chat Completions 入口。

Hub: [`docs/architecture/README.md`](../../docs/architecture/README.md)。

## Ownership

- Owner: TokenMarket Engineering
- Type: Go service
- Responsibilities: catalog admit, proxy-key auth, Project snapshot routing (shared qualify+score / dedicated fail-closed), native passthrough, usage observation. No user table. No plaintext Connection credentials in logs.

## Public paths

| Path | Notes |
|------|--------|
| `/openai/*` `/anthropic/*` `/vertex/*` | Native passthrough; mode and preview opt-in from authenticated Project, not request headers |
| `POST /v1/proxy/volcano/chat/completions` | V0.1 Volcano OpenAI-compat Chat Completions |
| `/health/live` `/health/ready` `/metrics` | Operational |

Contracts: `shared/contracts/native-passthrough/v1/`, `shared/contracts/endpoint-catalog/v1/`, `shared/contracts/route-decision/v1/`, `shared/contracts/volcano-openai-compat/v1/`.

Internal lookups go to api-service (`/internal/v1/proxy-keys/by-hash`, `/internal/v1/projects/{id}/route-snapshot`). Do not log snapshot credentials.

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
```

Capacity wall-clock soaks (`CAPACITY_FULL=1`) are opt-in; default `make test` / `make ci` skip them. Profile constants in `internal/capacity/profile.go` must not be shrunk.

## SF06 credential validation (internal)

Optional `POST /internal/v1/provider-credentials/validate` stays loopback-isolated outside local/dev. Use a synthetic token in local env only, never a production secret. See `shared/contracts/volcano-key-validation/v1/`.
