# Contract: Continuous Integration Quality Gate

**Version**: 1.0.0

**Adapter**: GitHub Actions default; root workflow is platform-independent

## Long-lived branches

| Branch | Role |
|--------|------|
| `master` | Production branch. Always releasable; sole source line for production deploys. |
| `master-dev` | Test-environment deployment branch. Integration and pre-production validation land here first. |

Feature work merges into `master-dev`. Production promotion is a reviewed merge from `master-dev` (or a hotfix PR) into `master`. Branch names record the **deploy line of code**, not the Make environment selector: migration and future deploy commands still require explicit `mode=local|test|prod` per `environment-mode.md`.

## Triggers

- Pull request opened, reopened, synchronized or otherwise updated against `master` or `master-dev`.
- Push to `master` or `master-dev` to verify the final merge commit.
- Manual `workflow_dispatch` for safe re-validation.
- `merge_group` when merge queue is enabled (for `master` and `master-dev`).

Core gates use no path filters. PR runs for the same branch may cancel stale runs; pushes to `master` and `master-dev` may not be cancelled by a later push.

## Required job

- Stable check name: `quality-gate`.
- Project command: `make ci` only.
- Any required step failure fails the job; no `continue-on-error`.
- Branch protection/ruleset requires this check on both long-lived branches and prevents force-push, deletion, direct push and bypass.

## Permissions and trust

- Workflow permissions: `contents: read`; all unlisted permissions are none.
- Checkout does not persist credentials and fetches sufficient history for secret scanning.
- Untrusted PR code runs under `pull_request`, never `pull_request_target`.
- No repository, organization, cloud or production secrets are consumed.
- Tests use synthetic, unusable configuration only.
- The workflow cannot publish packages/images, deploy, approve PRs or write repository content.
- Official Actions are pinned to full commit SHA; third-party tools are fixed by checksum or container digest.

## Blocking evidence

| Gate | Evidence |
|------|----------|
| Toolchains | Declared tool versions and lockfiles verified under an explicit toolchain execution profile (default `local`; GitHub Actions sets `TOKENMARKET_TOOLCHAIN_PROFILE=github-actions-ubuntu-24.04` with runner-provided `GITHUB_ACTIONS=true` and `RUNNER_OS=Linux`). Hosted Docker versions use an exact-list allowlist in `ops/workflow/toolchains.json`; unknown profiles and unapproved versions fail closed |
| Bootstrap | Frozen workflow/Go/Python/npm dependency preparation succeeds twice without changing lockfiles or resolution |
| Format | Non-modifying check passes; clean checkout remains format-idempotent |
| Type/lint/boundary | Independent `type-check` and aggregated lint pass for every applicable component and repository boundary |
| Tests | Every required component executes at least one real smoke test |
| Contracts | Schemas, ownership, versions, links and generated drift pass |
| Migrations | Offline validation plus pinned isolated PostgreSQL 15 API→Billing forward/backout/retry/final-head restoration pass |
| Secrets/dependencies | Full-history secret scan and Go/Python/npm locked dependency scans pass |
| Build | Five immutable images and three deterministic asset archives build |
| Runtime smoke | Every image runs as non-root and becomes healthy; expected endpoints respond |
| Image security | HIGH/CRITICAL scan passes or time-bounded approved exception is present |

## Cache policy

Caches contain downloads only and are keyed by OS, exact toolchain version and relevant lockfile hashes. `node_modules`, virtual environments, scanners, build output, credentials and configuration are never cached. No broad restore key may change dependency resolution. A cache miss affects speed only; disabling caches must not change correctness.

## Recovery and rollback

- Platform/transient scanner download failures remain failed and may be manually re-run; one bounded idempotent download retry is allowed.
- Suspected cache contamination is recovered by bumping cache schema or disabling cache.
- CI/tool upgrade rollback reverts workflow SHA, Make adapter and version source together while retaining job name `quality-gate`.
- A failed `master` or `master-dev` merge is recovered through a reviewed revert PR from the last known green commit; no forced reset or check bypass.
- A real secret finding requires immediate revoke/rotate and usage audit before any minimal, approved history remediation.
- Suppressions require rule/vulnerability ID, analysis, owner, approver, issue and expiry.
