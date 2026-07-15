# US4 Evidence: Local/CI Parity

**Story**: User Story 4 — 在本地与持续集成中获得相同结论  
**Feature**: `specs/001-repository-workflow-baseline/`  
**Date**: 2026-07-14  
**Commit**: repository state under implementation (design baseline unchanged)

## Scope

This evidence records that the repository root workflow produces the same step
sequence locally and in the GitHub Actions thin adapter, that `mode` selection
cannot be implicitly escalated, that dirty worktrees and special paths are
handled safely, and that the CI gate fails closed on any required step.

## T083–T089: Contract Tests

| Test file | Result |
|-----------|--------|
| `tests/workflow/test_paths.py` | 2/2 passed |
| `tests/workflow/test_dirty_format.py` | 2/2 passed |
| `tests/workflow/test_mode.py` | 7/7 passed |
| `tests/workflow/test_retry_safety.py` | 1/1 passed |
| `tests/workflow/test_accessibility_performance.py` | 3/3 passed |
| `tests/workflow/test_ci_contract.py` | 4/4 passed |
| `tests/workflow/test_reproducibility.py` | 2/2 passed |

Full `tests/workflow` regression: **185 passed**.

## T090–T096: Implementation

### Mode enforcement (`tools/workflow/mode.py`)

- `validate_mode` accepts `command` and `command line` origins for `test`/`prod`.
- `environment`, `file`, `shell`, `override` from unsafe origins are rejected.
- `prod` requires explicit approval via interactive phrase or `approval_proof`.

### Root workflow (`Makefile` / `tools/workflow/cli.py`)

New public target:

```text
make ci
```

Fixed ordering defined in root `Makefile`:

```text
toolchain-check → bootstrap → fmt-check → type-check → lint → test →
migrate-check → migrate-integration-check → security-check → build →
runtime-smoke → image-scan
```

`runtime-smoke` and `image-scan` are implemented in `tools/workflow/images.py`
and exposed through `workflow.cli`.

### GitHub Actions thin adapter (`.github/workflows/ci.yml`)

- Job name: `quality-gate`
- Runner: `ubuntu-24.04`
- Triggers: `push` to `main`, `pull_request`, `merge_group`, `workflow_dispatch`
- Permissions: `contents: read`
- Checkout: pinned `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683` with
  `fetch-depth: 0` and `persist-credentials: false`
- Setup actions pinned by full SHA:
  - `actions/setup-go@f111f3307d8850f501ac008e886eec1fd1932a34`
  - `actions/setup-node@cdca7365b2dadb8aad0a33bc7601856ffabcc48e`
  - `astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86`
- Only project command: `make ci`
- No path filters, secrets, publishing, or write permissions.

### Component `fmt-check`

All eight components expose a non-mutating `fmt-check` target:

- `services/proxy-gateway/Makefile`
- `services/api-service/Makefile`
- `services/billing-service/Makefile`
- `services/admin-service/Makefile`
- `frontend/Makefile`
- `shared/Makefile`
- `infra/Makefile`
- `ops/Makefile`

## Local `make ci` Run

Command executed:

```bash
PATH="/Users/token/.local/go1.25.12/bin:/Users/token/.local/bin:/Users/token/go/bin:/Users/token/.nvm/versions/node/v24.18.0/bin:$PATH" make ci
```

Results:

| Step | Result |
|------|--------|
| `toolchain-check` | PASSED |
| `bootstrap` | PASSED |
| `fmt-check` | PASSED (9/9) |
| `type-check` | PASSED (9/9) |
| `lint` | PASSED (9/9) |
| `test` | PASSED (9/9) |
| `migrate-check` | PASSED |
| `migrate-integration-check` | PASSED (PG15 forward/backout/retry) |
| `security-check` | **FAILED** — pip-audit reports known `starlette 0.45.3` vulnerabilities |
| `build` | PASSED (9/9) |
| `runtime-smoke` | PASSED (5/5 images healthy, non-root) |
| `image-scan` | **FAILED** — Trivy 0.61.0 not installed locally |

Exit code: `2` (security-check fail-closed)

The `security-check` failure is the expected fail-closed behavior for the
already-known `starlette 0.45.3` findings recorded in `us2-security-evidence.md`.
The `image-scan` failure is environmental (Trivy not present on the local
workstation); the CLI returns `TOOL_MISSING` and fails closed rather than
silently skipping the scan.

## Mode Matrix

| Command | Expected | Verified |
|---------|----------|----------|
| `make migrate` | mode=local default | PASSED |
| `mode=test make migrate` | accepted (command origin) | PASSED |
| `mode=prod make migrate` | rejected before resource access (no approval) | PASSED |
| `MODE=test make migrate` | rejected (environment origin) | PASSED |

## Dirty Worktree / Special Path Notes

- `make fmt` only touches declared source files; `.gitignore` preserves untracked files.
- Root resolution uses the workflow script location, so the repository can be checked
  out under paths containing spaces or non-ASCII characters.
- Retry safety: non-`fmt` actions do not mutate the worktree; `fmt` idempotency is
  verified by component formatters.

## Known Blockers for a Green Hosted Gate

1. **Trivy installation** — `image-scan` requires Trivy 0.61.0 on the runner.
2. **starlette vulnerability** — `security-check` requires a reviewed dependency
   update or an explicit, expiring exception before the gate can pass.

Both are tracked as fail-closed outcomes, not CI adapter bugs.

## T097: Onboarding Path

See `specs/001-repository-workflow-baseline/quickstart.md` and the updated
`README.md` (Phase 7) for the checkout-to-first-`make ci` path.

## T098/T099: Runbook & Ruleset

Recorded in `ops/runbooks/workflow.md`:

- CI cache contamination recovery.
- Runner/scanner failure handling.
- Failed `main` review-revert process.
- Required check rollout order.
- GitHub ruleset configuration for `quality-gate`, main protection, and bypass
  prevention.
- Linking PR and final-main `quality-gate` runs.
