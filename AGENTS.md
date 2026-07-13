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

- `make dev`: start PostgreSQL, Redis, Kafka, and Grafana for local development.
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

The repository has no commit history yet. Follow the mandated Conventional Commits style, such
as `feat: add gateway health check` or `docs: clarify migration policy`. PRs must describe scope,
link the relevant spec or issue, list verification evidence, call out contract/schema/security
impact, and include rollout and rollback notes. Include screenshots for visible frontend changes.

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
- Until SF02 implements the local dependency lifecycle, `make dev` and `make dev-down` must fail
  with `SF02_NOT_READY` before reading configuration or accessing Docker. Their public names stay
  stable when SF02 replaces the internal adapter.
- SF01 scaffolds operational health, metrics, tests and immutable builds only; it must not add
  buyer, seller, provider-Key, proxy, metering, billing or administration business behavior.
