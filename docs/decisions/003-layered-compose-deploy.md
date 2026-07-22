# ADR 003: Layered Docker Compose and Deploy Entry Isolation

**Status**: Accepted  
**Implementation Verification**: Pending — Phase 1 freezes contracts and Compose assets; runtime lifecycle lands in a later change after SF02 public activation evidence.  
**Date**: 2026-07-22  
**Owner**: TokenMarket Engineering  
**Deciders**: Repository maintainers / Platform team

## Context

TokenMarket develops with **host processes for application code** and **Docker only for middleware** on developer machines. Test and production hosts run **application containers built by `make build`**. Early architecture notes sketched a single root `docker-compose.yml` that mixed both models; ADR 002 already forbids business services in the local dependency Compose file.

Without an explicit layer model and Make isolation, teams will either:

1. Expand `infra/docker/compose.local.yml` and break SF02 contracts, or  
2. Invoke ad-hoc `docker compose` and bypass mode gates, redaction, and project identity.

## Decision

Adopt four layers and two Make surface families:

| Layer | Asset | Contents | Public entry |
|-------|--------|----------|--------------|
| **L — Local deps** | `infra/docker/compose.local.yml` | PostgreSQL, Redis, Grafana only (ADR 002) | `make dev` / `make dev-down` (`mode=local` only) |
| **I — Images** | Component Dockerfiles | Five immutable service/static images | `make build` (+ CI smoke/scan) |
| **A — App services** | `infra/docker/compose.app.yml` | gateway, api, billing, admin, frontend as **pre-built images** | Not invoked alone |
| **D — Deploy stack** | `infra/docker/compose.deploy.yml` (includes middleware + app) | Full stack for shared hosts | `make deploy` / `make deploy-down` with required `mode=test\|prod` |

### Additional rules

1. **Never** add business services, Kafka, or frontend to `compose.local.yml`.
2. Deploy middleware lives in `infra/docker/compose.middleware.yml` (same dependency digests as the local manifest) and is **not** a byte-include of `compose.local.yml`, because project identity, labels, and secret namespaces differ.
3. Deploy Compose files use `image:` only — **no** `build:` keys. Image production remains `make build`.
4. `make deploy` does **not** run migrations or builds; operators run `make build`, then `make deploy mode=…`, then `make migrate mode=…` as separate audited steps.
5. Project names: local keeps `tokenmarket-<12-hex>`; deploy uses fixed `tokenmarket-test` / `tokenmarket-prod`. Commands never adopt the other family's projects.
6. Mode selection reuses `environment-mode.md` (explicit command-line only; never Git branch inference). Production requires the existing approval path.
7. Until the deploy adapter is implemented, public `deploy` / `deploy-down` fail closed **before** Docker, config files, or network access (Phase 1 gate), analogous to the SF01 `SF02_NOT_READY` pattern, using a stable existing diagnostic until event contracts can add a dedicated code under a reviewed event version change.
8. Ordinary `deploy-down` never deletes named volumes.

## Ownership

- **Layer L**: Repository workflow maintainers (ADR 002).
- **Layer I**: Each component owner for its Dockerfile; workflow owner for aggregate `build`.
- **Layers A/D and deploy adapter**: Infrastructure + repository workflow maintainers.
- **Security review**: Required for publish policy, secret transport, image digest, or remote Docker endpoint changes.

## Options considered

### Single root compose for all environments

Rejected. Local process development and shared-host full-stack deployment have incompatible identity, hot-reload, and success criteria.

### Include `compose.local.yml` inside deploy

Rejected. Workspace-hash projects, loopback URL derivation from `.env.local`, and SF02 secret variable names must not become deploy facts.

### Shell-only `docker compose` wrappers

Rejected. Mode gates, redaction, locks, and event contracts already live in the Python workflow tool.

## Failure modes and controls

| Failure | Behavior |
|---------|----------|
| `make deploy` without `mode=test\|prod` | `INVALID_MODE` before resources |
| `make deploy mode=local` | Rejected; local stack is process + `make dev` |
| `make dev mode=test\|prod` | Rejected (local lifecycle only) |
| Deploy invoked before adapter lands | Fail closed; no Docker mutation |
| Missing built images at deploy time | Fail with recovery pointing at `make build` (Phase 2+) |
| Volume delete on ordinary down | Forbidden |

## Rollout

1. **Phase 1 (this ADR)**: contracts under `shared/contracts/deploy-environment/v1/`, Compose scaffolds, structural tests, Make/help surface, fail-closed CLI.
2. **Phase 2**: `tools/workflow/deploy_env/` adapter for `mode=test`.
3. **Phase 3**: `mode=prod` with approval, digest-pinned image policy hardening.
4. SF02 public activation (T074) remains independent and must not block Phase 1 docs; deploy runtime should not ship before Layer L is trustworthy for developers.

## Rollback

Revert deploy adapter, Compose app/middleware/deploy assets, and public target wiring together. Never delete deploy PostgreSQL volumes as part of rollback. Layer L and ADR 002 remain unchanged.

## Consequences

### Positive

- Clear developer vs operator paths with one root Makefile.
- SF02 boundary protected by separate files and tests.
- Reuses mode, approval, redaction, and event machinery.

### Negative

- Two middleware Compose definitions to keep digest-aligned (enforced by tests against `ops/workflow/local-dependencies.json`).
- V0.1 production is single-host Compose, not Kubernetes (future ADR if needed).

## Non-goals

- Kafka in the V0.1 deploy stack
- Local full-stack Compose for day-to-day coding
- Registry push/pull automation
- Multi-host orchestration

## References

- `docs/decisions/002-local-compose-lifecycle.md`
- `shared/contracts/deploy-environment/v1/lifecycle.md`
- `shared/contracts/local-environment/v1/lifecycle.md`
- `shared/contracts/repository-workflow/v1/environment-mode.md`
- `infra/docker/README.md`
