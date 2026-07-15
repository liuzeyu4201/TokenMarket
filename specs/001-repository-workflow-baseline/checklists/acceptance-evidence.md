# Acceptance Evidence: Repository Workflow Baseline

**Feature**: `specs/001-repository-workflow-baseline/`  
**Date**: 2026-07-14  
**Environment**: macOS, local workstation

## 1. Prerequisites

```bash
make help
make toolchain-check
make bootstrap
```

- `make help`: completed in <2 seconds, listed all public/support targets.
- `make toolchain-check`: PASSED for Make, Go 1.25.12, Python 3.11.15, uv 0.11.3,
  Node 24.18.0, npm 11.16.0, Docker 29.5.3, golangci-lint 1.64.8.
- `make bootstrap`: PASSED for all eight components; lockfiles unchanged.

## 2. Synthetic local configuration

```bash
cp .env.example .env.local
git status --short
```

- `.env.local` does not appear in `git status` (ignored).
- `.env.example` contains only names, comments and unusable placeholders.

## 3. Successful root and supporting actions

```bash
make fmt           # PASSED
make fmt-check     # PASSED
make type-check    # PASSED
make lint          # PASSED
make test          # PASSED
make build         # PASSED
```

- All eight components ran real adapters.
- Five immutable service images built with version tags; no `:latest` tag.
- Second `make fmt` produced no new differences.

## 4. Dirty-worktree formatting safety

Covered by `tests/workflow/test_dirty_format.py` and executed via `make test`.
Disposable repository copy verified that `make fmt` preserves pre-existing
changes, untracked files and out-of-scope content, and produces zero additional
differences on the second run.

## 5. SF02 transition behavior

```bash
make dev       # FAILED with SF02_NOT_READY
make dev-down  # FAILED with SF02_NOT_READY
```

- Diagnostic code `SF02_NOT_READY` returned.
- No Docker invocation, configuration read, or worktree mutation occurred.

## 6. Environment-mode safety

```bash
make migrate mode=PROD   # FAILED INVALID_MODE
make migrate             # effective mode local
mode=prod make migrate   # FAILED INVALID_MODE (shell origin rejected)
make migrate mode=prod   # FAILED PROD_APPROVAL_REQUIRED
```

All failures occurred before configuration, DNS or network access.

## 7. Migration ownership and round-trip

```bash
make migrate-check              # PASSED
make migrate-integration-check  # PASSED
```

- Owners: `api-service` then `billing-service`; `admin-service` non-owner.
- Single head and valid upgrade/downgrade metadata for each owner graph.
- PostgreSQL 15 fixture performed forward/backout/retry/final-head cleanly.

## 8. Path and terminal accessibility

```bash
NO_COLOR=1 make help  # plain text, no color escape codes
make test             # path fixture with spaces and CJK characters passed
```

## 9. Security gates

```bash
make security-check  # FAILED fail-closed: pip-audit reports starlette 0.45.3
make image-scan      # FAILED fail-closed: Trivy 0.61.0 not installed locally
```

Both failures are environmental/known-vulnerability outcomes, not bypasses.

## 10. Complete local CI gate

```bash
make ci  # FAILED at security-check (starlette known vulnerabilities)
```

Steps before the failure: toolchain-check, bootstrap, fmt-check, type-check,
lint, test, migrate-check, migrate-integration-check all PASSED. build and
runtime-smoke PASSED when executed independently.

## 11. Hosted CI

- `.github/workflows/ci.yml` exists and invokes only `make ci`.
- Job name `quality-gate`, runner `ubuntu-24.04`, permissions `contents: read`.
- Actions pinned by full SHA; `persist-credentials: false`.
- Hosted run evidence to be attached after first PR merge.

## 12. No business behavior introduced

- No buyer, seller, provider-key, proxy, metering, billing or administration
  business logic added.
- No production credentials, resources or deployments touched.
