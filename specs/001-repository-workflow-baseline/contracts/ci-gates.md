# Contract: Continuous Integration Quality Gate

**Version**: 1.0.0

**Adapter**: GitHub Actions default; root workflow is platform-independent

## Triggers

- Pull request opened, reopened, synchronized or otherwise updated against `main`.
- Push to `main` to verify the final merge commit.
- Manual `workflow_dispatch` for safe re-validation.
- `merge_group` when merge queue is enabled.

Core gates use no path filters. PR runs for the same branch may cancel stale runs; `main` runs may not be cancelled by a later push.

## Required job

- Stable check name: `quality-gate`.
- Project command: `make ci` only.
- Any required step failure fails the job; no `continue-on-error`.
- Branch protection/ruleset requires this check and prevents force-push, deletion, direct push and bypass.

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
| Toolchains | Exact supported versions and all lockfiles verified |
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
- A failed `main` merge is recovered through a reviewed revert PR from the last known green commit; no forced reset or check bypass.
- A real secret finding requires immediate revoke/rotate and usage audit before any minimal, approved history remediation.
- Suppressions require rule/vulnerability ID, analysis, owner, approver, issue and expiry.
