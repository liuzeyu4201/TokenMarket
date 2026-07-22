# Feature: Layered Compose Deploy Stack

**Feature Branch**: `003-layered-compose-deploy`  
**Feature ID**: matches directory basename (required by `ops/runbooks/workflow.md`)

## Intent

Separate **local development** (host processes + SF02 middleware via `make dev`) from
**test/prod single-host Docker** (`make deploy` / `make deploy-down` with
`mode=test|prod`).

## Authoritative design

| Artifact | Role |
|----------|------|
| [`docs/decisions/003-layered-compose-deploy.md`](../../docs/decisions/003-layered-compose-deploy.md) | ADR 003 — layers L / I / A / D, Make entries, non-goals |
| [`shared/contracts/deploy-environment/v1/lifecycle.md`](../../shared/contracts/deploy-environment/v1/lifecycle.md) | Public deploy contract |
| [`infra/docker/compose.{middleware,app,deploy}.yml`](../../infra/docker/) | Compose assets |
| [`ops/runbooks/deploy.md`](../../ops/runbooks/deploy.md) | Operator runbook |
| [`tools/workflow/deploy_env/`](../../tools/workflow/deploy_env/) | Workflow adapter |

SF02 local deps remain under `specs/002-local-dependency-lifecycle/` and
`infra/docker/compose.local.yml`. This feature must not expand `compose.local.yml`
with business services.

## Status

Implementation of the deploy stack MVP is on branch `003-layered-compose-deploy`.
Further contract/test hardening may extend this directory (spec/plan/tasks) without
renaming the feature id.
