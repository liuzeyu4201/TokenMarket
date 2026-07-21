# Docker infrastructure assets

Local container orchestration definitions. The lifecycle of PostgreSQL, Redis
and Grafana is owned by feature SF02: `compose.local.yml` is consumed only by
the repository workflow adapter behind the root `make dev` / `make dev-down`
targets, which verifies the committed bytes, pipes them to the Compose CLI
over stdin, and always supplies an explicit project name and a secure runtime
project directory. Never invoke this file directly with `docker compose up`.

## Three-service Compose model

`compose.local.yml` defines exactly three services — `postgres`, `redis`,
`grafana` — and nothing else. The service names are the canonical DNS names on
the single project-scoped default network; no fixed container names, no extra
networks, no startup-ordering links. All resources (containers, the default
network, both named volumes) are scoped to the per-workspace Compose project
`tokenmarket-<workspace-hash>` and labeled with `com.tokenmarket.repository`,
`com.tokenmarket.workspace-id`, and the full 64-hex
`com.tokenmarket.workspace-fingerprint`.

## Immutable image policy

Images are referenced only as `repository:tag@sha256:index-digest`, byte-equal
to the reviewed runtime manifest `ops/workflow/local-dependencies.json`:

- PostgreSQL `15.18-bookworm` (PostgreSQL License)
- Redis `7.2.14-bookworm` (BSD 3-Clause)
- Grafana OSS `13.0.3` (AGPL-3.0, unmodified local use)

Each digest is a multi-platform OCI index covering `linux/amd64` and
`linux/arm64`; per-platform child digests, licenses, and scan evidence are
recorded in ADR 002 (`docs/decisions/002-local-compose-lifecycle.md`). A tag or
digest change is a reviewed dependency change: tag, index digest, both child
digests, and scan evidence move together. Floating tags are never allowed.

## Loopback and network addresses

Every published port uses long syntax bound to `127.0.0.1` only. Host port
values are never hardcoded: the adapter derives them from the validated
loopback URLs in the ignored local configuration and injects them at runtime.
Container-side addresses on the project network are stable: `postgres:5432`,
`redis:6379`, `grafana:3000`.

### Runtime interpolation contract

The adapter supplies every value through a dedicated child-process environment
mapping (never a dotenv file, never the caller's shell):

| Variable | Content |
|----------|---------|
| `TOKENMARKET_WORKSPACE_ID` | Compose project identity `tokenmarket-<12-hex>` |
| `TOKENMARKET_WORKSPACE_FINGERPRINT` | Full 64-hex workspace fingerprint |
| `TOKENMARKET_POSTGRES_HOST_PORT` | Host port from `DATABASE_URL` |
| `TOKENMARKET_REDIS_HOST_PORT` | Host port from `REDIS_URL` |
| `TOKENMARKET_GRAFANA_HOST_PORT` | Host port from `GRAFANA_URL` |
| `TOKENMARKET_POSTGRES_USER` | Non-secret PostgreSQL user from `DATABASE_URL` |
| `TOKENMARKET_POSTGRES_DB` | Non-secret PostgreSQL database from `DATABASE_URL` |
| `TOKENMARKET_POSTGRES_PASSWORD` | Secret source for `postgres_password` |
| `TOKENMARKET_REDIS_CONFIG` | Secret source for `redis_config` |
| `TOKENMARKET_GRAFANA_ADMIN_PASSWORD` | Secret source for `grafana_admin_password` |

## Persistence classes

- **PostgreSQL — durable fact**: project-scoped named volume `postgres-data`
  mounted at `/var/lib/postgresql/data`; retained across ordinary down/up,
  retries, and failures.
- **Redis — preserved but rebuildable**: project-scoped named volume
  `redis-data` mounted at `/data`; ordinary down keeps it, but correctness
  never depends on its contents.
- **Grafana — ephemeral**: no volume at all. `/var/lib/grafana` is an explicit
  tmpfs `rw,mode=0700,uid=472,gid=472` so the container runs and writes as its
  verified non-root identity without creating an anonymous volume. Dashboards,
  data sources, and alerting remain SF19 scope.

Ordinary `down --remove-orphans` never passes volume-deletion, image-removal,
or prune flags, so named volumes always survive; service stop grace periods
are 60s (PostgreSQL) and 30s (Redis, Grafana).

## Secret transport

Secrets never appear in the YAML, service environment, command arguments,
host files, or image layers. Top-level Compose `secrets` use `environment`
sources resolved from the dedicated child mapping, and each service mounts its
secret with long syntax as a `0400` file owned by the verified upstream
non-root UID/GID:

- PostgreSQL: `999:999`, consumed through `POSTGRES_PASSWORD_FILE`.
- Redis: `999:999`; the secret is a generated `redis.conf` containing exactly
  one `requirepass <value>` directive, loaded via
  `redis-server /run/secrets/redis.conf` so the password never becomes a
  process argument.
- Grafana: `472:472`, consumed through `GF_SECURITY_ADMIN_PASSWORD__FILE`;
  the administrator name is the committed non-secret constant `admin`.

Healthchecks are authenticated and read secrets only from the mounted files:
PostgreSQL runs `psql` `SELECT 1` with `PGPASSWORD` sourced from the secret
file, Redis runs `redis-cli PING` with `REDISCLI_AUTH` extracted from the
mounted config (never `-a`), and Grafana checks `/api/health` for a healthy
database plus a Basic-auth `/api/user` confirming `isGrafanaAdmin`. These are
supplementary evidence; the workflow adapter's own bounded probes remain
authoritative.

## No-business-service boundary

This file must never gain Kafka/Redpanda, Prometheus, Loki, MinIO, the
frontend, the Go gateway, or any Python business service, and it performs no
migration, schema creation, seeding, or credential rotation. Lifecycle
ordering, locking, port preflight, image pulling, and readiness deadlines are
owned by the workflow adapter, not by this definition.

Structural invariants of this file are enforced by
`infra/tests/test_local_compose.py`.
