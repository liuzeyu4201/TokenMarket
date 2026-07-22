# ops/

Operational assets: migration ownership registry, monitoring/backup/runbooks and
workflow tooling. SF01 validates these assets and bundles them deterministically.

## Local environment (SF02)

- Manifest: `ops/workflow/local-dependencies.json` (PostgreSQL 15.18, Redis 7.2,
  Grafana OSS 13.0; multi-platform digests only).
- Runbook: [`runbooks/local-environment.md`](runbooks/local-environment.md).
- Public `make dev` / `make dev-down` stay fail-closed (`SF02_NOT_READY`) until
  Linux x86_64 and macOS arm64 lifecycle, isolation, persistence, redaction,
  recovery, and performance evidence pass and activation lands in one change.
- Supported host platforms for SF02: macOS arm64 and Linux x86_64.
- Business services are not started by `make dev`; only API Service and Billing
  Service implement PostgreSQL readiness probes in this feature.

## Deploy stack (ADR 003)

- Compose layers: `infra/docker/compose.middleware.yml`, `compose.app.yml`,
  `compose.deploy.yml` (never expand `compose.local.yml` with apps).
- Contract: `shared/contracts/deploy-environment/v1/lifecycle.md`.
- Runbook: [`runbooks/deploy.md`](runbooks/deploy.md).
- Public `make deploy` / `make deploy-down` require `mode=test|prod` and remain
  fail-closed until the deploy adapter is implemented.
