# Implementation Plan: 仓库工程工作流基线

**Branch**: `001-repository-workflow-baseline` *(feature identifier; no branch hook ran)* | **Date**: 2026-07-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-repository-workflow-baseline/spec.md`

## Summary

Create TokenMarket's first executable monorepo baseline: eight explicit component boundaries, five minimal deployable service/frontend scaffolds, three verifiable asset components, a root Make workflow with stable locked-dependency bootstrap and type-check commands, safe configuration and migration-mode contracts, and an actual blocking CI adapter. Every required component will perform real format, type, lint, smoke-test and build work while exposing no TokenMarket business behavior.

The implementation is contract-first and test-first. A small, owned repository-workflow tool reads a versioned component manifest and emits validated JSON Lines evidence; the root Makefile remains the only public entry. GitHub Actions is a read-only thin adapter that runs `make ci`. SF02 remains responsible for real local dependency lifecycle, so `dev` and `dev-down` fail early with `SF02_NOT_READY` and no side effects until that capability is delivered.

## Technical Context

**Language/Version**: GNU Make 3.81-compatible syntax and POSIX shell for orchestration; Go 1.25.12 for `proxy-gateway`; Python 3.11.15 for workflow tooling and three services; Node 24.18.0 LTS with strict TypeScript for frontend; YAML/JSON/JSON Schema/OpenAPI for contracts and CI

**Primary Dependencies**: Gin and Prometheus-compatible Go metrics; FastAPI, Pydantic, Uvicorn and Prometheus client for Python services; React 18, Vite, Vitest/Testing Library, ESLint and Prettier for frontend; one uv-locked environment for maintained repository workflow tooling plus independent uv locks per Python service; npm with `package-lock.json`; Docker BuildKit; GitHub Actions thin adapter; Gitleaks, govulncheck, pip-audit, npm audit and Trivy for security gates

**Storage**: No TokenMarket business storage or schema. Durable engineering facts are Git-tracked component/migration manifests, schemas, lockfiles and documentation. CI uses an isolated PostgreSQL 15 instance with synthetic credentials only for migration round-trip evidence. Workflow events/build reports are ephemeral and must contain no secrets or personal data.

**Testing**: Go `testing` with race detection and coverage; pytest/pytest-asyncio for repository workflow tooling and each Python service; Vitest and Testing Library for frontend; repository workflow contract/negative tests in `tests/workflow/`; pinned PostgreSQL 15 container migration forward/backout/retry/head-restore integration; container runtime health smoke; schema, link, boundary and deterministic-archive tests

**Target Platform**: macOS and Linux developer hosts; Linux containers; GitHub-hosted `ubuntu-24.04` CI. Service images are built for the current validated platform in SF01; multi-architecture publishing is out of scope.

**Project Type**: Polyglot monorepo containing a developer CLI/workflow, four backend service scaffolds, one web frontend scaffold, versioned contracts and infrastructure/operations assets

**Performance Goals**: `make help` completes within 2 seconds; missing/unsupported tool or invalid configuration/mode fails within 5 seconds before side effects; incremental commands never reinstall all dependencies unconditionally; all SC-001–SC-012 thresholds are exercised in automated or documented validation

**Constraints**: Root Makefile is the only public workflow; `bootstrap` installs only lock-resolved project dependencies after toolchain validation and never installs system tools or rewrites locks; no business endpoints or data tables; no real credentials or `.env.*` except safe examples; no cross-service storage/imports; no fixed absolute paths; paths with spaces/Chinese supported; dirty-worktree formatting cannot reset/delete/out-of-scope-modify; `mode` is exact lowercase and production needs a second gate; `dev`/`dev-down` must not inspect Docker before SF02; CI is read-only and does not publish or deploy

**Scale/Scope**: Eight required boundaries, five immutable service/frontend images, three deterministic asset archives, seven stable public targets plus stable `bootstrap`/`type-check` and controlled support targets, two migration owners, one blocking CI job and four developer/operational contract families

**Affected Components**: `services/proxy-gateway/`, `services/api-service/`, `services/billing-service/`, `services/admin-service/`, `frontend/`, `shared/`, `infra/`, `ops/`, root workflow/tooling, documentation and `.github/workflows/`

**Contracts**: Developer CLI/exit/output contract, workflow event JSON Schema, component manifest JSON Schema, environment-mode contract, migration owner manifest JSON Schema, CI gate contract and minimal service health OpenAPI. No TokenMarket buyer/seller/provider HTTP or event contract is introduced.

**Data & Migrations**: `api-service` then `billing-service` are declared migration owners; `admin-service` is a non-owner and cannot access their storage. SF01 initializes real Alembic graphs without business tables. Offline `migrate-check` validates one head, naming, upgrade/downgrade and backout links; CI uses PostgreSQL 15 for forward/backout/retry. `make migrate` never starts a database and validates `mode`/approval before configuration or network access.

**Security & Privacy**: Synthetic configuration only; `.env` and `.env.*` ignored except safe examples; secret values never committed, logged, cached, placed in fixtures or build args. CI permissions are `contents: read`, checkout credentials are not persisted, no secrets are available, and untrusted PRs use `pull_request`. Scans fail closed; exceptions require ID, owner, approval, issue and expiry.

**Observability & Reliability**: Workflow emits redacted JSONL step events with run ID, component, action, status, stable code and duration plus accessible plain text. Backend scaffolds provide request IDs, structured safe logs, `/health/live`, `/health/ready`, `/metrics`; readiness has no SF02 dependency. Required actions fail fast, are safely retryable, and never report skipped work as passed.

**Deployment & Rollback**: SF01 creates buildable images and CI but performs no production deployment or publishing. Rollout is a reviewed PR, CI activation and repository ruleset requiring stable `quality-gate`. Rollback is a reviewed revert PR that keeps the required job name stable; there are no business data changes. Tool upgrades roll back workflow SHA, version files and adapters together.

## Constitution Check

*GATE: passed before Phase 0 and re-checked after Phase 1 design.*

### Pre-Research Gate

| Gate | Status | Evidence / Decision |
|------|--------|---------------------|
| Architecture and ownership | PASS | Uses only constitution-approved boundaries; workflow tooling is repository tooling, not a new runtime service; no cross-service storage/imports |
| Contracts and compatibility | PASS | Developer and health contracts are designed before implementation; public Make targets remain stable |
| Security and privacy | PASS | No real secrets, production values or write-capable CI; scans and pre-side-effect mode validation planned |
| Data correctness | PASS | No business data; explicit migration owners, order, offline validation and PostgreSQL round-trip/backout evidence |
| Testing | PASS | Tests/negative fixtures precede every adapter and scaffold; race/type/contract/migration/container evidence defined |
| Operations | PASS | Separate live/ready, metrics, request IDs, safe logs, workflow evidence, failure codes and runbook owner planned |
| Delivery | PASS | Locked maintained toolchains, immutable images, actual blocking CI, rollback and traceability are included |

No gate requires an exception. GitHub Actions is a new delivery adapter rather than a runtime service; an ADR is still planned because the repository has no existing remote and the choice must be replaceable.

### Post-Design Gate

| Gate | Status | Phase 1 evidence |
|------|--------|------------------|
| Architecture and ownership | PASS | [data-model.md](./data-model.md) defines eight boundaries, action ownership and prohibited dependencies |
| Contracts and compatibility | PASS | [contracts/](./contracts/) defines Make, event, component, mode, migration, CI and health behavior with versioning |
| Security and privacy | PASS | Environment/CI contracts fail before secret or resource access; quickstart uses only synthetic data |
| Data correctness | PASS | Migration entities, owner manifest schema and isolated round-trip procedure are explicit; no business schema exists |
| Testing | PASS | [quickstart.md](./quickstart.md) plus the verification matrix below cover positive, negative, recovery and reproducibility evidence |
| Operations | PASS | Health OpenAPI, JSONL event schema, stable codes and runbook paths are defined |
| Delivery | PASS | CI gate, immutable build evidence, activation and revert procedures are specified |

Post-design result: **PASS — no unresolved clarification or unjustified constitution violation.**

## Project Structure

### Documentation (this feature)

```text
specs/001-repository-workflow-baseline/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── make-workflow.md
│   ├── workflow-event.schema.json
│   ├── component-manifest.schema.json
│   ├── environment-mode.md
│   ├── migration-manifest.schema.json
│   ├── ci-gates.md
│   └── service-health.openapi.yaml
└── tasks.md                       # Created later by /speckit-tasks
```

### Source Code (repository root)

```text
Makefile                            # Only public workflow entry
README.md                           # Checkout-to-first-verification guide
.env.example                       # Safe names/comments/placeholders only
.gitignore
.tool-versions                     # Maintained language/tool version source
.github/
├── workflows/ci.yml               # Thin adapter: make ci
├── dependabot.yml                 # Optional platform supplement, not core gate
└── CODEOWNERS                     # Workflow/contract ownership
docs/
├── api/README.md
└── decisions/
    └── 001-github-actions-ci-adapter.md
tools/workflow/                    # Maintained internal workflow tool, not a one-off script
├── __init__.py
├── pyproject.toml                 # Locked repository-tool test/format/type environment
├── uv.lock
├── cli.py                         # Manifest orchestration, safe output, mode validation
├── events.py
├── manifest.py
├── migrations.py                 # Offline checks and isolated PostgreSQL 15 round-trip
├── mode.py
└── security.py
tests/workflow/
├── test_foundational_contracts.py
├── test_command_contract.py
├── test_component_manifest.py
├── test_dirty_format.py
├── test_migrations.py
├── test_mode.py
├── test_paths.py
├── test_sf02_transition.py
└── fixtures/
ops/workflow/
├── components.json                # Single component/action fact source
└── toolchains.json                # Version/integrity fact source
services/
├── proxy-gateway/
│   ├── cmd/gateway/main.go
│   ├── internal/httpserver/
│   │   ├── server.go
│   │   └── server_test.go
│   ├── internal/observability/
│   ├── go.mod
│   ├── go.sum
│   ├── .golangci.yml
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── Makefile                   # Internal adapter only
│   └── README.md
├── api-service/
│   ├── app/{__init__.py,main.py,health.py,observability.py}
│   ├── tests/test_health.py
│   ├── alembic/{env.py,versions/}
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── Makefile
│   └── README.md
├── billing-service/               # Same minimal Python shape + owned Alembic graph
└── admin-service/                 # Same runtime shape, no migration ownership
frontend/
├── src/{main.tsx,App.tsx,App.test.tsx}
├── index.html
├── nginx.conf
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
├── vitest.config.ts
├── eslint.config.js
├── .prettierrc
├── Dockerfile
├── .dockerignore
├── Makefile
└── README.md
shared/
├── contracts/
│   ├── README.md
│   └── _meta/contract-manifest.schema.json
├── tests/
├── Makefile
└── README.md
infra/
├── docker/README.md
├── nginx/README.md
├── grafana/README.md
├── kafka/README.md
├── tests/
├── Makefile
└── README.md
ops/
├── migrations/{owners.json,README.md}
├── monitoring/README.md
├── backup/README.md
├── runbooks/{workflow.md,migrations.md}
├── tests/
├── Makefile
└── README.md
```

**Structure Decision**: Keep every approved runtime boundary from the constitution, but create only layers with immediate verified value. The five deployable components receive minimal health/metrics runtime code; `shared`, `infra` and `ops` receive versioned assets, negative tests and deterministic bundles. No empty business/domain package, copied shared model, cross-service repository or placeholder business route is created.

## Implementation Strategy

### Phase A — Contracts and failing workflow tests

1. Add the GitHub Actions adapter ADR before creating CI configuration.
2. Build the isolated workflow test harness and write failing tests for absent or invalid runtime contract copies, component/toolchain manifests and migration-owner manifests.
3. Materialize component/toolchain/migration manifests from the Phase 1 schemas only after those foundational tests fail for the missing runtime facts.
4. Write root workflow tests first for command discovery, locked/idempotent bootstrap, explicit type-check, required action bindings, JSONL events, safe paths, dirty formatting, mode origin, production approval and SF02 transition.
5. Add negative fixtures for missing component, empty adapter, zero tests, boundary violation, contract drift, invalid mode, secret detection and migration graph errors.

**Exit evidence**: Tests fail for the expected missing workflow/scaffold behavior and validate the Phase 1 contracts.

### Phase B — Root workflow and safe configuration

1. Initialize a dedicated uv-locked environment for `tools/workflow`; implement the small package using Python 3.11 standard library where practical. It is a maintained internal tool with pytest, format and type evidence, not a one-off script.
2. Implement the root Make targets and internal component adapters without duplicating component lists. `bootstrap` validates system toolchains first, then performs only frozen Go/uv/npm dependency preparation; `type-check` is independently callable and remains part of `lint`.
3. Add safe `.env.example`, ignore rules, toolchain preflight, redacted JSONL/plain-text output and link/structure checks.
4. Implement `mode=local|test|prod` origin validation and production double gate before configuration/resource access.
5. Implement `dev`/`dev-down` blocked adapters that fail before Docker/config access.

**Exit evidence**: Workflow contract tests pass; two frozen bootstrap runs leave lockfiles unchanged; `type-check`, help and preflight thresholds pass; side-effect snapshots remain unchanged for rejected actions.

### Phase C — Minimal component scaffolds

1. Implement gateway health/readiness/metrics, request ID and structured logging with Go tests first.
2. Implement the same operational contract independently in each Python service with pytest tests first; initialize Alembic only for API and billing owners.
3. Implement minimal accessible frontend page, tests and unprivileged runtime health behavior.
4. Implement shared/infra/ops validators, negative tests and deterministic bundles.
5. Add per-component internal Make adapters, lockfiles, Dockerfiles and `.dockerignore` files.

**Exit evidence**: All eight components produce real fmt/lint/test/build evidence; five images run healthy as non-root; unknown business paths return 404.

### Phase D — Migration, security and reproducibility gates

1. Add migration owner reconciliation and offline graph checks, then implement `migrate-integration-check` using a pinned PostgreSQL 15 image with synthetic credentials. It must run API then Billing forward migration, backout, retry and final-head restoration without `make dev` or shared databases.
2. Add full-history secret scan, locked dependency scans and immutable image scan through root targets.
3. Pin tools, Actions and base images by exact version plus integrity reference.
4. Prove deterministic asset archives and repeated builds on the same commit.

**Exit evidence**: `make migrate-check`, `make migrate-integration-check`, `make security-check`, `make build`, runtime smoke and `make image-scan` all pass; the isolated database returns to both declared heads, and synthetic negative fixtures are detected and redacted.

### Phase E — CI activation and documentation

1. Add `.github/workflows/ci.yml` with read-only permissions, full-history checkout, pinned toolchain/scanner setup and the single project command `make ci`; Docker provides the isolated PostgreSQL and image-smoke environments.
2. Add CODEOWNERS and repository setup instructions for required `quality-gate`, protected `master` / `master-dev` and merge queue compatibility.
3. Complete root/component READMEs and ops runbooks; validate all links.
4. When a GitHub remote exists, configure the rulesets and prove PR plus final `master` / `master-dev` triggers. Until then the workflow file is testable locally, but hosted acceptance is not complete.

**Exit evidence**: Full [quickstart.md](./quickstart.md) passes and PR review evidence links every requirement to tests/gates.

## Verification Matrix

| Requirement area | Planned automated evidence | Manual/review evidence |
|------------------|----------------------------|------------------------|
| US1 / FR-003–014 | Command contract, frozen bootstrap, explicit type-check, component-action, fail-fast, preflight, fmt idempotency, SF02 and migration tests | Help text and recovery review |
| US2 / FR-015–018 | `.env` ignore test, safe placeholder rules, Gitleaks fixture, log/event redaction, lockfile checks | Confirm no real value in Git/history/build args |
| US3 / FR-001–002, FR-019, FR-024 | Manifest schema, structure/boundary negative fixtures, contract drift and link checks | ADR/owner/compatibility review |
| US4 / FR-020–026 | Path fixture, dirty-worktree snapshot, mode-origin matrix, CI config contract and required gate test | Hosted PR/`master`/`master-dev` gate evidence and ruleset review |
| ER-001–003 | Contract version/compatibility tests, approval-before-access, pinned PostgreSQL 15 migration forward/backout/retry/head-restore | Security and migration owner review |
| ER-004–007 | Help/preflight timing, retry/repeat runs, JSONL schema, `NO_COLOR`, screen-reader-safe text | Recorded target environment and recovery evidence |
| SC-001–012 | Quickstart scenarios plus automated counts/timing/side-effect snapshots | New-developer 15-minute exercise and hosted CI proof |

## Test-First Order

For each slice, add or update a test that fails for the missing behavior before implementation:

1. Foundational runtime contract/manifest fixtures that fail before runtime facts are materialized.
2. Root workflow unit and subprocess tests.
3. Component health/metrics/request-ID tests.
4. Component lint/type/boundary tests.
5. Component build and container smoke tests.
6. Migration forward/backout/retry and invalid-mode tests.
7. Secret/dependency/image scan positive fixtures.
8. CI YAML and local/hosted parity tests.

Changed Go/Python domain coverage threshold remains 80%; SF01 creates no domain package, so the threshold is not fabricated. Operational scaffold packages still require direct behavior and negative assertions.

## Rollout and Rollback

### Rollout

1. Merge contracts, manifests and tests with the smallest coherent scaffold implementation in one focused feature branch.
2. Require local `make ci` on a clean checkout.
3. Create the hosted CI workflow and verify read-only permissions before enabling the required check.
4. Enable `quality-gate` ruleset only after one successful PR run exists, preventing a missing-check deadlock.
5. Verify final `master` SHA, immutable image references and scan evidence; no images are pushed or deployed.

### Rollback

- Revert through a reviewed PR validated by the same `quality-gate`; never reset or force-push `master` or `master-dev`.
- Keep the required job name stable; revert Action SHAs, toolchain files and Make adapters together.
- Disable a contaminated cache by schema bump; correctness must remain with caches off.
- No database schema or production resource exists to roll back. If a migration test fixture fails, discard the isolated instance and fix the migration graph.
- A real secret finding triggers revoke/rotate and audit before any reviewed history remediation; CI never rewrites history automatically.

## Complexity Tracking

No constitution violations or temporary exceptions are planned. The internal workflow package and manifests are justified by the feature's core need for a single machine-readable component/command fact source; they do not introduce a runtime service, datastore or cross-service dependency.
