# Docker infrastructure assets

Container orchestration is **layered**. The root Makefile is the only public
entry; do not run these Compose files with a bare `docker compose up`.

## Layer map (ADR 003)

| Layer | File | Purpose | Public Make entry |
|-------|------|---------|-------------------|
| **L — Local deps** | `compose.local.yml` | PostgreSQL, Redis, Grafana for developers | `make dev` / `make dev-down` |
| **A — Apps** | `compose.app.yml` | Five application services (images only) | Included by deploy only |
| **Middleware (deploy)** | `compose.middleware.yml` | Same three deps for shared hosts | Included by deploy only |
| **D — Deploy stack** | `compose.deploy.yml` | `include` of middleware + apps | `make deploy` / `make deploy-down` |

| Environment | Application | Middleware |
|-------------|-------------|------------|
| Local | Host processes | Layer L |
| Test / Prod | Layer A containers | Layer D middleware |

Image production is Layer I: component Dockerfiles via `make build`.

## Local dependencies (`compose.local.yml`)

Owned by SF02 / ADR 002. Exactly three services — `postgres`, `redis`,
`grafana` — and nothing else. Invoked only through the workflow adapter, which
verifies committed bytes, pipes them over stdin, and supplies an explicit
project name `tokenmarket-<workspace-hash>` plus a secure runtime project
directory.

### Immutable image policy (local and deploy middleware)

Images are `repository:tag@sha256:index-digest`, aligned with
`ops/workflow/local-dependencies.json`:

- PostgreSQL `15.18-bookworm`
- Redis `7.2.14-bookworm`
- Grafana OSS `13.0.3`

Floating tags are never allowed. Digest changes are reviewed dependency PRs.

### Local loopback and secrets

Host ports bind `127.0.0.1` only and come from validated `.env.local` URLs.
Secrets use Compose environment-source secret files (0400, non-root UIDs).
See ADR 002 and `ops/runbooks/local-environment.md`.

### No-business-service boundary

`compose.local.yml` must never gain Kafka, Prometheus, Loki, MinIO, the
frontend, the Go gateway, or any Python business service. Structural tests:
`infra/tests/test_local_compose.py`.

## Deploy stack (`compose.deploy.yml`)

Owned by ADR 003. Merges deploy middleware and application services for
`mode=test` or `mode=prod` project names `tokenmarket-test` /
`tokenmarket-prod`.

Rules:

- Application services reference **pre-built** images only (`image:`; no `build:`).
- Operator path: `make build` → `make deploy mode=…` → `make migrate mode=…`.
- Ordinary `deploy-down` retains PostgreSQL/Redis named volumes.
- Until the deploy adapter is implemented, public targets fail closed before
  Docker access (see `shared/contracts/deploy-environment/v1/lifecycle.md`).

Structural tests: `infra/tests/test_app_compose.py`,
`infra/tests/test_deploy_compose.py`.

## Superseded sketches

Root-level full-stack `docker-compose.yml` examples in older `项目开发/`
architecture notes are historical product sketches. Runtime truth is ADR 002,
ADR 003, and the files in this directory.
