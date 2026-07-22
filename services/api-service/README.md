# API Service

TokenMarket core API service scaffold (SF01) with SF02 PostgreSQL readiness.

## Ownership

- Owner: TokenMarket Engineering
- Type: Python FastAPI service
- Migration owner: yes (order 1)

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

## Local dependency readiness (SF02)

- The service starts independently of `make dev`. It does **not** manage the
  local PostgreSQL lifecycle; run `make dev` first when a database is required.
- `/health/live` remains process-only and stays HTTP 200 while the process is up.
- `/health/ready` performs one owned, non-retried async `SELECT 1` against
  `DATABASE_URL` with a two-second bound. Failure returns the contracted HTTP
  503 body naming only `postgres` and a stable safe code (no URLs, secrets, or
  exception bodies).
- When PostgreSQL returns, readiness recovers to the unchanged HTTP 200 shape
  without restarting the process.
- Metrics: probe total/failure counters and duration histogram use secret-free
  bounded labels only.
