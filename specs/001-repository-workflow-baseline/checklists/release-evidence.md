# Release Evidence

**Feature**: `specs/001-repository-workflow-baseline/`  
**Date**: 2026-07-14  
**Commit SHA**: `b3c6fbef5804ff8439ab8d65885915fa4bc5cc68`

## Final local `make ci`

```bash
make ci
```

Result: **FAILED at security-check** (exit 2)

Sequence:

| Step | Result |
|------|--------|
| `toolchain-check` | PASSED |
| `bootstrap` | PASSED |
| `fmt-check` | PASSED (9/9) |
| `type-check` | PASSED (9/9) |
| `lint` | PASSED (9/9) |
| `test` | PASSED (9/9) |
| `migrate-check` | PASSED |
| `migrate-integration-check` | PASSED |
| `security-check` | **FAILED** — pip-audit starlette 0.45.3 findings |
| `build` | not reached |
| `runtime-smoke` | not reached |
| `image-scan` | not reached |

The failure is the known, fail-closed outcome documented in
`security-evidence.md`. No business logic or unexpected worktree drift was
introduced.

## Immutable artifacts

### Container images

| Component | Image tag |
|-----------|-----------|
| proxy-gateway | `tokenmarket/proxy-gateway:0.1.0` |
| api-service | `tokenmarket/api-service:0.1.0` |
| billing-service | `tokenmarket/billing-service:0.1.0` |
| admin-service | `tokenmarket/admin-service:0.1.0` |
| frontend | `tokenmarket/frontend:0.1.0` |

### Asset archives

| Component | Archive | SHA-256 |
|-----------|---------|---------|
| shared | `shared/dist/shared-assets.tar.gz` | deterministic per build |
| infra | `infra/dist/infra-assets.tar.gz` | deterministic per build |
| ops | `ops/dist/ops-assets.tar.gz` | deterministic per build |

## Hosted `quality-gate`

- Workflow: `.github/workflows/ci.yml`
- Job name: `quality-gate`
- Only project command: `make ci`
- Hosted run URLs for PR and final `master` / `master-dev` commit to be attached after the first
  merged PR.

## Rollout / rollback notes

- The CI adapter is thin and replaceable; project logic remains in the root
  Makefile and `tools/workflow/`.
- Rollback of a broken CI change uses a reviewed revert PR protected by the
  same `quality-gate`.
- The `starlette` dependency finding must be resolved or formally excepted
  before the hosted gate can turn green.
