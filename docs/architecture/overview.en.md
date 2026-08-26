[中文](overview.md) | **English**

# V0.1 as-built architecture

This page describes **paths that already run in the repository**, not the full product diagram on the roadmap. Target architecture (later Kafka, MinIO, billing loop) remains [`项目开发/1-项目架构与目录结构.md`](../../项目开发/1-项目架构与目录结构.md).

## Processes and ports

`make start` brings these up locally. Middleware ports come only from `.env.local` URLs; app ports may be overridden with `*_HOST_PORT`.

| Process | Default | Duty |
|---------|---------|------|
| frontend | `:5173` | Register, login, dashboard placeholder |
| api-service | `:8000` | Users, session, authorization, seller keys, buyer proxy keys; internal routing lookups |
| proxy-gateway | `:8080` | Public proxy, health, metrics; optional loopback credential validation |
| billing-service | `:8001` | Health / ready scaffold |
| admin-service | `:8002` | Health scaffold |
| PostgreSQL | `:5432` | System of record |
| Redis | `:6379` | Rate limit and session assist; never the sole copy of durable facts |
| Grafana | `:3000` | V0.1 proxy overview dashboard |

## Request paths

```text
Buyer OpenAI-compatible client
    Authorization: Bearer <proxy key>
    POST /v1/proxy/volcano/chat/completions
                    │
                    ▼
            proxy-gateway
         1. Authenticate proxy key     ──internal──► api-service /internal/v1/proxy-keys/by-hash
         2. Pick key excluding self    ──internal──► api-service /internal/v1/seller-keys/routable
         3. Volcano Chat Completions (allowlisted fields; missing usage must not be filled with 0)
         4. Usage observation / structured logs / Prometheus metrics
                    │
                    ▼
            Volcano upstream

Browser
    /register  /login  /dashboard
                    │
                    ▼
            frontend  ──/api/v1──►  api-service
                                    POST /auth/register
                                    POST /auth/verification-challenges
                                    POST /auth/sessions
                                    /seller-keys  /proxy-keys
                                    /authorization/evaluate
```

Successful proxy bodies and started SSE stay OpenAI-shaped. Pre-stream failures use the unified `{code,message,data,request_id,timestamp}` envelope.

## Ownership

- The gateway **must not** own the users table or seller-key ciphertext; routing goes through api-service internal APIs.
- api-service owns `users`, keys, and authorization audit. Startup **never** auto-migrates.
- billing-service is the second migration owner and **does not** debit or invoice in V0.1.
- Local Compose contains only PostgreSQL / Redis / Grafana. Kafka is not an SF02 dependency.

## Related contracts

- [`shared/contracts/volcano-openai-compat/v1/`](../../shared/contracts/volcano-openai-compat/v1/)
- [`shared/contracts/phone-auth-session/v1/`](../../shared/contracts/phone-auth-session/v1/)
- [`shared/contracts/user-registration/v1/`](../../shared/contracts/user-registration/v1/)
- [`shared/contracts/role-access-isolation/v1/`](../../shared/contracts/role-access-isolation/v1/)
- [`shared/contracts/local-environment/v1/`](../../shared/contracts/local-environment/v1/)
