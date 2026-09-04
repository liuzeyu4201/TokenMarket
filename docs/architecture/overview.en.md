[中文](overview.md) | **English**

# V0.2 as-built architecture

This page describes **paths that already run in the repository**, not later money-loop items on the roadmap. Target architecture (later Kafka, MinIO, real payments) remains [`项目开发/1-项目架构与目录结构.md`](../../项目开发/1-项目架构与目录结构.md). Version scope: [`项目开发/V0.2/V0.2_0831/README.md`](../../项目开发/V0.2/V0.2_0831/README.md).

## Processes and ports

`make start` brings these up locally. Middleware ports come only from `.env.local` URLs; app ports may be overridden with `*_HOST_PORT`.

| Process | Default | Duty |
|---------|---------|------|
| frontend | `:5173` | Register, login, Projects / Bindings / Connections, seller supply, `/admin` |
| api-service | `:8000` | Users, session, authz, Project, Binding, Connection, proxy keys; internal routing snapshots |
| proxy-gateway | `:8080` | Native passthrough, Volcano compat entry, health, metrics |
| billing-service | `:8001` | Test-quota ledger, quotes, recon |
| admin-service | `:8002` | Isolated admin session and ops surface |
| PostgreSQL | `:5432` | System of record |
| Redis | `:6379` | Rate limit and session assist; never the sole copy of durable facts |
| Grafana | `:3000` | Proxy and SLO dashboards |

## Request paths

```text
Buyer native SDK
    Authorization: Bearer <tmk-… proxy key>
    /openai/*  |  /anthropic/*  |  /vertex/*
                    │
                    ▼
            proxy-gateway
         1. Authenticate proxy key + Project snapshot  ──internal──► api-service
            /internal/v1/proxy-keys/by-hash
            /internal/v1/projects/{id}/route-snapshot
         2. Catalog admit (stable endpoints; Preview needs Project preview_opt_in)
         3. Shared: hard qualify then score; dedicated: exclusive, fail-closed
         4. Same-protocol passthrough; prefer upstream spend, else usage × rates
         5. Undetermined cost → unresolved, never recorded as 0
                    │
                    ▼
            OpenAI / Anthropic / Vertex

V0.1 compat entry still mounted:
    POST /v1/proxy/volcano/chat/completions  →  Volcano OpenAI-compat Chat Completions

Browser
    /register  /login  /projects  /connections  /supply  /admin/login
                    │
                    ▼
            frontend  ──/api/v1──►  api-service
                                    /auth/*  /projects  /bindings
                                    /connections  /proxy-keys
            /admin/*  ────────────►  admin-service (separate cookie)
```

Successful data-plane bodies keep each vendor’s native shape. Control-plane and **pre-proxy** failures use `{code,message,data,request_id,timestamp}`.

## Ownership

- The gateway **must not** own the users table or Connection plaintext; routing uses api-service internal snapshots.
- Project mode and `preview_opt_in` come from the authenticated Project record, **not** from request headers.
- api-service owns `users`, Projects, Bindings, Connection ciphertext, and authorization audit. Startup **never** auto-migrates.
- billing-service owns the test-quota ledger. V0.2 **does not** recharge, withdraw, or peg to fiat.
- Local Compose contains only PostgreSQL / Redis / Grafana. Kafka is not an SF02 dependency.

## Related contracts

- [`shared/contracts/native-passthrough/v1/`](../../shared/contracts/native-passthrough/v1/)
- [`shared/contracts/endpoint-catalog/v1/`](../../shared/contracts/endpoint-catalog/v1/)
- [`shared/contracts/project/v1/`](../../shared/contracts/project/v1/)
- [`shared/contracts/provider-binding/v1/`](../../shared/contracts/provider-binding/v1/)
- [`shared/contracts/provider-connection/v1/`](../../shared/contracts/provider-connection/v1/)
- [`shared/contracts/route-decision/v1/`](../../shared/contracts/route-decision/v1/)
- [`shared/contracts/ledger/v1/`](../../shared/contracts/ledger/v1/)
- [`shared/contracts/phone-auth-session/v1/`](../../shared/contracts/phone-auth-session/v1/)
- [`shared/contracts/volcano-openai-compat/v1/`](../../shared/contracts/volcano-openai-compat/v1/)
