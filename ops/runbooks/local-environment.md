# Local Environment Runbook (SF02)

Owner: repository workflow owner

Public entry points: `make dev`, `make dev-down`. The lifecycle adapter is
implemented and exercised by guarded tests; public targets remain
`SF02_NOT_READY` until dual-platform evidence (Linux x86_64 + macOS arm64),
usability protocol, and atomic activation (T074) complete. See
`specs/002-local-dependency-lifecycle/evidence/README.md`.

## Safe inspection

- Prefer root Make targets and workflow events; do not copy secrets into shell
  history.
- Inspect project containers with exact Compose project labels
  (`com.docker.compose.project=tokenmarket-<hash>`). Never use a workspace path
  filter.
- Named volumes `*_postgres-data` and `*_redis-data` are retained across ordinary
  `dev-down`. Grafana uses tmpfs only.

## Common recovery

| Symptom | Action |
|---------|--------|
| `INVALID_MODE` | Use omitted mode or `mode=local` on the command line only |
| `INVALID_CONFIG` | Fix field **names** in ignored `.env.local` (never paste secrets into tickets) |
| `PORT_CONFLICT` | Free the loopback port or change only the matching URL port |
| `OPERATION_IN_PROGRESS` | Wait for the other lifecycle operation; retry the same command |
| `DEPENDENCY_NOT_READY` / timeout | Inspect retained containers; fix auth/runtime; rerun `make dev` |
| `RESOURCE_OWNERSHIP_CONFLICT` | Do not adopt foreign resources; use the owning workspace |
| Moved workspace finding | Recover from the original path identity; report-only resources are never stopped by the new path |
| Interrupted start/stop | Rerun the same target; state is retained for direct convergence |
| Credential drift in PostgreSQL volume | Stop is still safe without config; start fails closed until credentials match the volume |

## Non-destructive stop

`make dev-down` stops and removes only exact-project containers and networks,
with `--remove-orphans`, and **never** passes `--volumes`, `--rmi`, or prune.
Repeat stops are idempotent success when already stopped.

## Accessibility

Workflow output is `NO_COLOR`-safe plain text or JSONL, without icons or
interactive prompts. Exit status alone is sufficient for success/failure.

## Evidence ownership

Cross-platform performance, persistence, recovery, and usability evidence is
recorded under `specs/002-local-dependency-lifecycle/evidence/` by the workflow
owner after the automated gates pass.
