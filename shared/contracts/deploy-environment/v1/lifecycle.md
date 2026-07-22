# Contract: Deploy Environment Lifecycle

**Version**: 1.0.0  
**Owner**: Repository and infrastructure maintainers  
**Audience**: Operators of test/production single-host stacks, CI maintainers, workflow adapters  
**Related**: ADR 003 (`docs/decisions/003-layered-compose-deploy.md`), local lifecycle v1 (SF02)

## Public invocation

The root Makefile remains the only public entry:

```text
make deploy mode=test|prod
make deploy-down mode=test|prod
```

Rules:

- `mode` is **required** and must be the command-line Make origin `mode=test` or `mode=prod`.
- Omitted mode, `mode=local`, shell-exported mode, or branch-inferred mode are invalid (`INVALID_MODE`) before configuration or Docker access.
- `mode=prod` additionally requires the production approval contract in `repository-workflow/v1/environment-mode.md` before any secret read or Docker mutation.
- Success is exit status 0; any failure is non-zero. Exact non-zero values are not stable API.

### Intentionally excluded

```text
make deploy mode=local     # forbidden — local apps are host processes
make dev mode=test|prod    # forbidden — Layer L is local-only
docker compose -f infra/docker/...   # not a public entry
```

## Layer map

| Layer | Committed asset | Role |
|-------|-----------------|------|
| L | `infra/docker/compose.local.yml` | Developer middleware only (ADR 002); never used by deploy |
| I | Component Dockerfiles | Built by `make build` into `tokenmarket/<id>:<tag>` |
| A | `infra/docker/compose.app.yml` | Five application services; image references only |
| Middleware (deploy) | `infra/docker/compose.middleware.yml` | PostgreSQL, Redis, Grafana for deploy projects |
| D | `infra/docker/compose.deploy.yml` | Merges middleware + app for `make deploy*` |

Middleware image tags and multi-platform OCI index digests MUST match `ops/workflow/local-dependencies.json` until a reviewed dependency change updates local and deploy definitions together.

## Project identity

| Mode | Compose project name | Labels |
|------|----------------------|--------|
| test | `tokenmarket-test` | `com.tokenmarket.repository=tokenmarket`, `com.tokenmarket.environment=test` |
| prod | `tokenmarket-prod` | same with `environment=prod` |

Deploy commands MUST NOT stop, adopt, or mutate local workspace projects (`tokenmarket-<12-hex>`). Local commands MUST NOT mutate deploy projects.

## Configuration

| Mode | Ignored config file | Template |
|------|---------------------|----------|
| test | `.env.test` | placeholders in `.env.example` (deploy section) |
| prod | `.env.prod` (or approved secret provider) | placeholders only |

Deploy configuration supplies middleware URLs/secrets and application settings. Real credentials are never committed. Application containers reach middleware via Compose DNS `postgres`, `redis`, and `grafana` on the project network.

## Application services (Layer A)

| Service name | Default image | Container port |
|--------------|---------------|----------------|
| `proxy-gateway` | `tokenmarket/proxy-gateway:0.1.0` | 8080 |
| `api-service` | `tokenmarket/api-service:0.1.0` | 8000 |
| `billing-service` | `tokenmarket/billing-service:0.1.0` | 8001 |
| `admin-service` | `tokenmarket/admin-service:0.1.0` | 8002 |
| `frontend` | `tokenmarket/frontend:0.1.0` | 3000 |

Compose definitions MUST use `image:` only. `build:`, root Compose files, and floating `:latest` tags are forbidden.

## Ordering relative to other targets

```text
make build
make deploy mode=test
make migrate mode=test
# ... operate ...
make deploy-down mode=test
```

- `make deploy` does not build images.
- `make deploy` does not run Alembic migrations.
- `make deploy-down` preserves PostgreSQL and Redis named volumes; it never passes volume-delete, image-remove, or prune flags.

## Readiness (runtime — Phase 2+)

After images exist and Compose reconcile succeeds, deploy readiness requires:

1. Middleware authenticated probes equivalent to SF02 intent (PostgreSQL query, Redis AUTH/PING, Grafana health/admin).
2. Each application `/health/live` success.
3. API and Billing may report PostgreSQL readiness separately; deploy success for V0.1 requires live probes for all five app services and three middleware services under one bounded deadline (to be fixed in the adapter implementation).

## Phase 1 gate (current executable)

Until the deploy adapter is implemented and verification evidence is recorded:

- `make deploy` and `make deploy-down` MUST fail closed before reading deploy env files, contacting Docker, or mutating resources.
- The failure message MUST name the gate and point at ADR 003 / this contract.
- The diagnostic code uses an existing workflow code stable in event schema v1 (`COMPONENT_NOT_INITIALIZED`) so the immutable v1 event contract is not expanded during the SF02 deprecation window. A dedicated `DEPLOY_NOT_READY` code may be introduced only with a reviewed event schema version change.

## Diagnostics (planned / stable)

In addition to shared workflow codes (`INVALID_MODE`, `INVALID_CONFIG`, `PROD_APPROVAL_REQUIRED`, `TOOL_MISSING`, …), deploy lifecycle may later emit dependency and ownership codes consistent with event v2 once the adapter lands.

Messages contain field names, component IDs, and repository-relative paths only — never secret values, raw connection URLs with userinfo, or workspace absolute paths.

## Persistence

| Store | Ordinary deploy-down |
|-------|----------------------|
| PostgreSQL named volume | Retained |
| Redis named volume | Retained (rebuildable content) |
| Grafana `/var/lib/grafana` | Ephemeral tmpfs (no durable volume until SF19 decision) |

Destructive reset is out of scope for this contract version.

## Compatibility

- Adding optional publish overlays is backward-compatible when default behavior stays safe.
- Renaming public targets, allowing `mode=local` for deploy, merging apps into `compose.local.yml`, or deleting volumes on ordinary down is breaking and requires a new contract version plus ADR amendment.
