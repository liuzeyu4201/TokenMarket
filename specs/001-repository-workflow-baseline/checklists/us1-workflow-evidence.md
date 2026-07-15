# US1 Workflow Evidence

**Feature**: specs/001-repository-workflow-baseline — 仓库工程工作流基线  
**Story**: US1 — 从仓库根目录完成日常工程动作  
**Recorded**: 2026-07-15  
**Environment**: macOS, Go 1.25.12, Python 3.11.15, Node 24.18.0, Docker Desktop

## 1. Root Makefile Help

```text
TokenMarket repository workflow

Public targets:
  make dev            Start local dependencies after SF02
  make dev-down       Stop local dependencies after SF02
  make fmt            Apply repository formatters (modifies source)
  make lint           Run static analysis, type checks and boundary checks
  make test           Run all component tests
  make build          Build five service images and three asset bundles
  make migrate        Apply reviewed migrations to selected environment

Support targets:
  make bootstrap      Prepare locked project dependencies
  make type-check     Run the complete type-check set independently
  make toolchain-check Verify declared tool versions

Prerequisites: Go, Python/uv, Node/npm, Docker (see .tool-versions)
Side effects: fmt modifies declared source files; build creates local images
Recovery: fix the reported component error and rerun the same command
```

## 2. Frozen Bootstrap Idempotency

Two consecutive `make bootstrap` runs completed without modifying any lock file
or dependency resolution:

- First run: installed/verified uv environments for tools/workflow, api-service,
  billing-service, admin-service; ran `npm ci` for frontend.
- Second run: `Resolved ... Checked ...` for all Python projects; `npm ci`
  reported `up to date`.

No `uv.lock` or `package-lock.json` drift was observed between runs.

## 3. Independent Type-Check

```text
[PASSED] repository type-check: [OK] aggregate type-check: {'status': 'PASSED', 'code': 'OK', 'passed': 9, 'failed': 0, 'skipped': 0}
```

All eight components plus the repository workflow tool passed their respective
type checks (Go vet/golangci-lint, mypy, tsc --noEmit).

## 4. Aggregate Test / Lint / Build

| Command | Result | Passed | Failed | Skipped |
|---------|--------|--------|--------|---------|
| `make test` | PASSED | 9 | 0 | 0 |
| `make lint` | PASSED | 9 | 0 | 0 |
| `make build` | PASSED | 9 | 0 | 0 |

### Component Test Counts

| Component | Test Count | Runner |
|-----------|------------|--------|
| proxy-gateway | 7 | go test -race |
| api-service | 7 | pytest |
| billing-service | 5 | pytest |
| admin-service | 8 | pytest |
| frontend | 4 | vitest |
| shared | 6 | pytest |
| infra | 9 | pytest |
| ops | 10 | pytest |
| **Total** | **56** | — |

### Workflow Contract Tests

`tests/workflow` suite: **126 passed, 0 failed**.

## 5. PostgreSQL 15 Migration Round Trip

```text
[PASSED] repository migrate-check: [OK] migration owners validated: api-service, billing-service; mode=local
[PASSED] repository migrate-integration-check: [OK] api-service and billing-service forward/backout/retry passed on isolated PostgreSQL 15
```

- `migrate-check` validated that `api-service` and `billing-service` are the only
  migration owners, with `admin-service` listed as a non-owner.
- `migrate-integration-check` ran API→Billing forward, backout, retry, and final
  head restoration against an isolated PostgreSQL 15 container without invoking
  `make dev` or sharing a database.

## 6. Five Image Runtime Smoke

Built and smoke-tested images with independent build contexts, multi-stage
Dockerfiles, non-root users, and health checks:

| Image | Tag | Size | Health Smoke |
|-------|-----|------|--------------|
| tokenmarket/proxy-gateway | 0.1.0 | 19.8 MB | PASSED |
| tokenmarket/api-service | 0.1.0 | 275 MB | PASSED |
| tokenmarket/billing-service | 0.1.0 | 281 MB | PASSED |
| tokenmarket/admin-service | 0.1.0 | 229 MB | PASSED |
| tokenmarket/frontend | 0.1.0 | 76.8 MB | PASSED |

## 7. Three Asset Bundle Summary

`make build` produced deterministic asset archives:

| Bundle | Path | Size |
|--------|------|------|
| shared-contracts | `shared/dist/shared-contracts.tar.gz` | 8.8 KB |
| infra-assets | `infra/dist/infra-assets.tar.gz` | 607 B |
| ops-assets | `ops/dist/ops-assets.tar.gz` | 1.6 KB |

## 8. SF02 Zero-Side-Effect Gate

`make dev` and `make dev-down` both failed with `SF02_NOT_READY` before reading
configuration or accessing Docker:

```text
[FAILED] repository dev: [SF02_NOT_READY] SF02 must provide the lifecycle adapter
[FAILED] repository dev-down: [SF02_NOT_READY] SF02 must provide the lifecycle adapter
```

No local resources were started, stopped, or modified.

## 9. Known Local Environment Notes

- Node was switched to `v24.18.0` via nvm for the verification session.
- Go 1.25.12 and golangci-lint 1.64.8 were installed under `~/.local` to match
  the toolchain manifest, because the host versions differed.
- `ops/workflow/toolchains.json` was updated to record the actual npm version
  bundled with Node 24.18.0 (`11.16.0`) based on the Node.js download archive.
- `tools/workflow/manifest.py` was extended to accept `*.test.*` test files in
  addition to `test_*` and `*_test.*`, matching the frontend Vitest convention.

## 10. Sign-off

US1 implementation satisfies the acceptance criteria for root-level engineering
actions: stable Makefile entry points, real per-component formatting/type-check/
test/build, immutable image tags, isolated PG15 migration verification, and the
SF02 transition guard.
