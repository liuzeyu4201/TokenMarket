# API Service

TokenMarket 领域 API：用户、会话、授权、Project、Binding、加密 Provider Connection、项目代理 Key。第一迁移所有者。

Hub: [`docs/architecture/README.md`](../../docs/architecture/README.md).

## Ownership

- Owner: TokenMarket Engineering
- Type: Python FastAPI service
- Migration owner: yes (order 1)
- Owns: `users`, Projects, Bindings, Connection ciphertext, proxy keys, authorization audit

Startup **never** auto-migrates. Apply with `make migrate`.

## Surfaces (V0.2)

- Auth: register, phone OTP, `__Host-` session, workspace switch
- Authorization evaluate and self-trade exclusion
- Projects (shared/dedicated; mode immutable; `preview_opt_in`)
- Provider Bindings and encrypted Connections (no plaintext read-back on public paths)
- Project-scoped proxy keys (`tmk-…`)
- Internal: `/internal/v1/proxy-keys/by-hash`, `/internal/v1/projects/{id}/route-snapshot` (dataplane credentials only on the internal token path)

Contracts under `shared/contracts/{user-registration,phone-auth-session,project,provider-binding,provider-connection,project-proxy-key,role-access-isolation}/v1/`.

## Commands

```bash
make bootstrap
make fmt
make type-check
make lint
make test
make build
make migrate
```

## Readiness (SF02)

- `/health/live` is process-only.
- `/health/ready` is one owned `SELECT 1` against `DATABASE_URL` (2s, no retry). Failures name only `postgres` — no URLs or secrets.
