# API Service

TokenMarket core API service scaffold (SF01) with SF02 PostgreSQL readiness and
user registration (`POST /api/v1/auth/register`, SF03 / feature `003-user-registration-ui`).

## Ownership

- Owner: TokenMarket Engineering
- Type: Python FastAPI service
- Migration owner: yes (order 1)
- User domain owner: this service (`users`, `registration_idempotency_records`)

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

## Registration (SF03)

- Contract: `shared/contracts/user-registration/v1/`
- Requires `DATABASE_URL` (migrated) and `REDIS_URL` for rate limiting (fail-closed if missing/down).
- Optional `CORS_ALLOW_ORIGINS` (default Vite local origins).
- Does **not** issue tokens (SF04).
- Migration: `alembic/versions/0002_users_registration.py` — `upgrade` creates tables;
  `downgrade` drops them. Apply with `make migrate` / Alembic; app startup never auto-migrates.
- **Backup**: tables inherit the API Service PostgreSQL platform backup/restore
  (see `ops/backup/README.md`). Soft-delete is not restore; idempotency rows are 24h auxiliary.
- Alerts / runbook: `ops/alerts/registration.yml`, `ops/runbooks/registration.md`.

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
