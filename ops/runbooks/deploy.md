# Deploy Stack Runbook (ADR 003)

Owner: repository workflow + infrastructure maintainers

Public entry points: `make deploy`, `make deploy-down` with **required**
`mode=test` or `mode=prod`. Until the deploy adapter is implemented, both
targets fail closed before Docker or deploy configuration access
(`COMPONENT_NOT_INITIALIZED` — see `shared/contracts/deploy-environment/v1/lifecycle.md`).

## Layer reminder

| Path | Role |
|------|------|
| Local coding | Host app processes + `make dev` middleware (`compose.local.yml`) |
| Test / prod host | `make build` → `make deploy mode=…` → `make migrate mode=…` |

Never run `docker compose -f infra/docker/compose.deploy.yml` directly.

## Planned happy path (after adapter lands)

```bash
make build
make deploy mode=test
make migrate mode=test
# operate / validate
make deploy-down mode=test
```

Production adds the existing production approval gate on `mode=prod`.

## Compose assets

- `infra/docker/compose.middleware.yml` — PostgreSQL / Redis / Grafana (deploy labels)
- `infra/docker/compose.app.yml` — five application images
- `infra/docker/compose.deploy.yml` — `include` merge

Project names: `tokenmarket-test`, `tokenmarket-prod`. Do not stop
`tokenmarket-<workspace-hash>` local projects from deploy commands.

## Safe inspection (future runtime)

- Prefer Make targets and workflow events.
- Inspect with Compose project name / labels
  (`com.tokenmarket.environment=test|prod`, `com.tokenmarket.stack=deploy`).
- Named volumes for PostgreSQL/Redis are retained across ordinary down.

## Recovery

| Symptom | Action |
|---------|--------|
| Gate / not initialized | Adapter not landed; do not bypass with raw Compose |
| `INVALID_MODE` | Pass explicit `mode=test` or `mode=prod` on the Make command line |
| Missing images (Phase 2+) | Run `make build` (or approved pull) then retry deploy |
| Port conflict | Free the host port or change deploy config ports |
| Partial start | Resources retained; fix cause and rerun `make deploy` |

## Non-destructive stop

`make deploy-down` must never pass `--volumes`, `--rmi`, or prune. Volume wipe
is out of scope for ordinary lifecycle.
