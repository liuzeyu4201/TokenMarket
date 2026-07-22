# ADR 001: GitHub Actions CI Adapter

**Status**: Accepted  
**Date**: 2026-07-13  
**Owner**: TokenMarket Engineering  
**Deciders**: Repository maintainers / Platform team

## Context

TokenMarket's monorepo needs a single, reproducible quality gate that runs the same commands locally and in hosted CI. The root Makefile is the only public workflow entry point. A hosted CI platform is required so that external reviewers can verify changes without relying on a developer's laptop.

GitHub Actions is chosen as the first hosted adapter because the repository is hosted on GitHub and the platform provides `ubuntu-24.04` runners, pinned Action SHAs, and read-only `contents` permissions. This ADR records the boundaries of that adapter so it can be replaced by another platform in the future without changing project behavior.

## Decision

Use a thin GitHub Actions workflow (`.github/workflows/ci.yml`) that performs no project logic itself. It checks out the repository, installs the exact toolchain versions declared in `.tool-versions`, and invokes the single project command:

```text
make ci
```

All formatting, type-checking, linting, testing, migration validation, security scanning, building and image scanning are delegated to the root Makefile and the repository workflow tooling under `tools/workflow/`.

## Ownership

- **Adapter owner**: Platform / repository maintainers.
- **Workflow behavior owner**: The root Makefile and `tools/workflow/` maintainers.
- **Component behavior owner**: Each component team owns its internal adapter (`Makefile`, tests, Dockerfile).
- **Security review**: Required for any change to permissions, checkout settings, runner choice, or pinned Action SHAs.

## Permissions

The workflow runs with the minimum permissions required to check out code and run the project command:

- `permissions.contents: read` only.
- No `packages: write`, `actions: write`, `id-token: write`, or repository secrets.
- Checkout does not persist credentials (`persist-credentials: false`).
- Full Git history is fetched (`fetch-depth: 0`) so that secret scanning can inspect the entire history.
- Untrusted pull requests run under the `pull_request` trigger only; `pull_request_target` is not used.

No cloud, production, or repository secrets are consumed by SF01. Tests use synthetic, unusable configuration only.

## Failure Modes

| Scenario | Behavior | Recovery |
|----------|----------|----------|
| Toolchain setup failure | Job fails; no project code runs. | Re-run after resolving runner/network issue; bounded idempotent download retry is allowed. |
| `make ci` step failure | Job fails; full logs and JSONL events are emitted. | Fix the cause locally, re-run `make ci`, push; no forced merge or bypass. |
| Scanner download failure | Fails closed; may be manually re-run once. | Disable cache or bump cache schema if contamination is suspected. |
| Cache contamination | Disable cache or bump cache schema; correctness must hold with caches off. | Re-run with cache disabled, then investigate. |
| Required check missing | Branch protection/ruleset prevents merge until `quality-gate` reports success. | Do not bypass; fix the workflow or the change. |
| `master` / `master-dev` merge failure | Revert through a reviewed PR validated by the same `quality-gate`. | No force-push, reset, or check bypass. |

The adapter does not transform failures into warnings, retry flaky tests until green, or skip required steps.

## Replacement Boundaries

The GitHub Actions file is a replaceable adapter. Replacing it with another CI platform (e.g., GitLab CI, Buildkite, self-hosted runner) is allowed if the replacement:

1. Invokes the same single project command `make ci`.
2. Uses the same pinned toolchain versions from `.tool-versions` and `ops/workflow/toolchains.json`.
3. Runs with equivalent read-only permissions and does not persist checkout credentials.
4. Does not introduce platform-specific project logic, path filters, or secret access.
5. Keeps the required check name stable as `quality-gate`.

Any change that alters the Makefile command contract, component manifest, or required check name is not a pure adapter replacement and requires its own ADR.

## Rollback

- A broken CI change is rolled back by reverting the workflow SHA, Makefile adapter, and version source files together in a reviewed PR.
- The required job name `quality-gate` stays stable across rollback.
- A contaminated cache is disabled by bumping the cache schema or running with caches off.
- A real secret finding triggers immediate credential revoke/rotate and usage audit before any history remediation; CI never rewrites history automatically.

## Consequences

### Positive

- Local and CI use the exact same commands and pass/fail semantics.
- The adapter is small enough to audit and replace.
- Read-only permissions and no secrets limit the blast radius of a compromised runner or malicious PR.

### Negative

- GitHub Actions runner availability and network access become a dependency for merge gating.
- A future platform migration must preserve the `quality-gate` name and the `make ci` contract.

## References

- `specs/001-repository-workflow-baseline/contracts/ci-gates.md`
- `specs/001-repository-workflow-baseline/contracts/make-workflow.md`
- `ops/workflow/components.json`
- `ops/workflow/toolchains.json`
