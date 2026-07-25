# Repository Guidelines

## Project Structure & Module Organization

The repository currently contains specifications and engineering standards. Read
`.specify/memory/constitution.md` before changing architecture or code. Product research lives
under `产品调研/`; implementation standards, the PRD, roadmap, and V0.1 spec live under
`项目开发/`.

Application code must follow the documented monorepo layout: `services/proxy-gateway/` for the
Go ingress, `services/{api,billing,admin}-service/` for FastAPI services, `frontend/` for the
React application, `shared/` for versioned contracts, and `infra/`/`ops/` for deployment,
monitoring, migrations, and runbooks. Keep tests within each component's established test root.

## Build, Test, and Development Commands

The root Makefile is the required workflow entry point as implementation is scaffolded:

- `make start` / `make stop`: local default — SF02 middleware plus five host
  application processes. `make dev` / `make dev-down`: middleware only
  (PostgreSQL 15, Redis 7, Grafana OSS). Kafka is out of the SF02 dependency
  set. Business services are host processes in local development — never added
  to `compose.local.yml`.
- `make deploy` / `make deploy-down`: test/prod full stack (middleware + five
  app images) per ADR 003. Require explicit `mode=test|prod`. Phase 1 fails
  closed before Docker; assets live under `infra/docker/compose.{middleware,app,deploy}.yml`.
- `make test`: run all Go, Python, and frontend test suites.
- `make lint`: run static analysis and type checks across components.
- `make fmt`: apply repository formatters.
- `make build`: build all service images.
- `make migrate`: apply reviewed Alembic migrations.

Do not add a one-off script when an existing Make target can be extended. Until the Makefile
lands, documentation-only changes require structural and link validation rather than app tests.

## Coding Style & Naming Conventions

Go code must pass `gofmt`, `go vet`, and `golangci-lint`; use lowercase package names and
`PascalCase` for exported identifiers. Python uses four spaces, `snake_case`, type annotations,
Black, isort, flake8, and mypy. React uses strict TypeScript, ESLint, and Prettier; name components
`PascalCase.tsx` and hooks `useSomething.ts`. Preserve service boundaries and define HTTP/event
contracts before consumers.

## Testing Guidelines

Write tests before implementation. Use Go's `testing` package with race detection and coverage;
use pytest, pytest-asyncio, and testcontainers for Python. Name Python tests `test_<behavior>.py`
and Go tests `*_test.go`. Changed Go and Python domain packages require at least 80% line
coverage, plus direct negative tests for authorization, idempotency, concurrency, and migrations.

## Commit & Pull Request Guidelines

Follow Conventional Commits (for example `feat: add gateway health check` or
`docs: clarify migration policy`). PRs must describe scope, link the relevant
spec or issue, list verification evidence, call out contract/schema/security
impact, and include rollout and rollback notes. Include screenshots for visible
frontend changes.

### Branch naming

Canonical rules live in `ops/runbooks/workflow.md`. Summary:

| Kind | Pattern | PR into |
|------|---------|---------|
| Production line | `master` (fixed) | — |
| Test line | `master-dev` (fixed) | — |
| Spec Kit feature | `NNN-short-kebab` **=** `specs/NNN-short-kebab/` only | `master-dev` |
| Product change (no Spec Kit feature) | `feat/<slug>` | `master-dev` |
| Bug fix | `fix/<slug>` | `master-dev` |
| Prod hotfix | `hotfix/<slug>` (from `master`) | `master`, then back-merge |
| Docs / chore / refactor | `docs|chore|refactor/<slug>` | `master-dev` |

Rules: lowercase ASCII kebab-case; no spaces/underscores; recommended ≤ 50 chars;
never use environment names (`local`/`test`/`prod`) as branches; never invent a
numbered `NNN-...` branch without a matching `specs/NNN-.../` directory; never
use `feat/002-...` / `feature/002-...` when a numbered Spec Kit feature exists.
Open PRs against `master-dev`. Promote to production with a reviewed PR into
`master` after test validation. Hotfixes that land on `master` must be
back-merged to `master-dev`. Make environment selection remains explicit
`mode=local|test|prod` and is never inferred from the Git branch name; see
`ops/runbooks/workflow.md` and `shared/contracts/repository-workflow/v1/`.

## Security & Configuration

Never commit `.env.*`, credentials, provider keys, or production data. Update `.env.example` with
safe placeholders only. Secrets must be encrypted, redacted from telemetry, and injected through
environment variables or an approved secret provider.

## Active Feature Context

- `001-repository-workflow-baseline`: planning artifacts live in
  `specs/001-repository-workflow-baseline/plan.md` with developer contracts under its
  `contracts/` directory.
- Planned maintained toolchains are Go 1.25.12, Python 3.11.15 with an independent workflow-tool
  lock plus per-service `uv.lock`, and Node 24.18.0 LTS with npm lockfiles; dependency or tool
  upgrades remain reviewed changes.
- The root Makefile remains the only public workflow. In addition to the seven public actions,
  stable `bootstrap` and `type-check` support commands are required; bootstrap prepares only
  committed-lock dependencies and never installs system tools or rewrites locks.
- GitHub Actions is a read-only thin adapter that invokes `make ci`; component commands and
  quality gates must not be duplicated in CI YAML. CI migration evidence uses a pinned isolated
  PostgreSQL 15 container for API-then-Billing forward/backout/retry/head restoration.
- SF02 public activation (T074) is complete: `make dev` / `make dev-down` and
  `make start` / `make stop` run the real local middleware lifecycle; public
  workflow events default to the v2 standard envelope. Historical
  `SF02_NOT_READY` remains only as deprecation-window documentation.
- SF01 scaffolds operational health, metrics, tests and immutable builds only; it must not add
  buyer, seller, provider-Key, proxy, metering, billing or administration business behavior.
- `002-local-dependency-lifecycle`: design and evidence live in
  `specs/002-local-dependency-lifecycle/`; ADR 002 implementation verification is
  **Verified**. Dual-platform lifecycle evidence (T069/T070) and owner usability
  evidence (T071) are recorded under `evidence/`.
- SF02 is limited to PostgreSQL 15.18, Redis 7.2 and Grafana OSS 13.0 fixed by reviewed
  multi-platform OCI index digests. It derives `tokenmarket-<workspace-path-hash>` project
  ownership, accepts only loopback `DATABASE_URL`/`REDIS_URL`/`GRAFANA_URL` facts from ignored
  `.env.local`, uses collision-checking full workspace fingerprints and Compose-managed non-root
  secret files, pipes verified committed Compose bytes through stdin with a safe hashed runtime
  project directory so Compose labels do not expose the workspace path, serializes lifecycle
  operations, preserves PostgreSQL/Redis named volumes, and gives Grafana explicit tmpfs storage
  on ordinary down.
- Only API Service and Billing Service gain PostgreSQL-aware readiness in SF02. Their liveness
  remains independent; Gateway and Admin Service must not gain undeclared dependency probes, and
  no business service becomes part of `make dev`.
- Layered Compose deploy (branch `feat/layered-compose-deploy`, **not** a Spec Kit
  `specs/NNN-...` feature): ADR 003 (`docs/decisions/003-layered-compose-deploy.md`),
  contracts under `shared/contracts/deploy-environment/v1/`, compose assets under
  `infra/docker/compose.{middleware,app,deploy}.yml`. Public entries: `make deploy` /
  `make deploy-down` with `mode=test|prod`. Do not expand `compose.local.yml` with
  business services or revive root-level full-stack compose sketches.
