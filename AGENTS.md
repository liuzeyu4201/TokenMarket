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
