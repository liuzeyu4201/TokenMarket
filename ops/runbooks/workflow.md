# Workflow Runbook

## Long-lived branches

| Branch | Role | Typical merge path |
|--------|------|--------------------|
| `master` | **Production branch** — always releasable; source for production deploys | Reviewed PR from `master-dev` or hotfix into `master` |
| `master-dev` | **Test-environment deployment branch** — integration and pre-prod validation | Feature / fix PR into `master-dev` |

These two names are fixed. Do not rename them, and do not invent additional long-lived
deploy lines without a reviewed contract change.

## Branch naming standard

All short-lived branches use **lowercase ASCII**, **kebab-case**, and **no spaces**.
Branch names never encode environment (`local` / `test` / `prod`); environment is always
selected with explicit `mode=` (see below).

### Grammar

```text
long-lived   := master | master-dev
spec-feature := <NNN>-<slug>                 # only when specs/NNN-slug/ exists
other        := <kind>/<slug>
kind         := feat | fix | hotfix | docs | chore | refactor
slug         := [a-z0-9]+(-[a-z0-9]+)*     # English words, hyphens only
NNN          := [0-9]{3}                     # zero-padded Spec Kit feature id
```

Recommended total length: **≤ 50 characters**. Avoid underscores, dots (except none),
uppercase, Chinese or other non-ASCII, personal names, and raw ticket IDs without a slug
(for example prefer `fix/gateway-request-id` over `fix/1234` alone).

### Feature branches (primary path)

When work has (or will have) a Spec Kit feature under `specs/`:

| Rule | Requirement |
|------|-------------|
| Name form | `NNN-short-kebab-description` |
| Identity | Branch basename **MUST equal** the feature directory under `specs/` |
| Base branch | Create from current green `master-dev` |
| PR target | `master-dev` |
| Examples | `001-repository-workflow-baseline`, `002-local-dependency-lifecycle` |

Allocate `NNN` in ascending order (next free three-digit id). Do not reuse an id for a
different feature. Do not invent a parallel name that differs only by prefix
(`feature/002-...` or `feat/002-...` is forbidden when a numbered Spec Kit feature exists).
Do **not** invent `NNN-...` branch names when there is no matching `specs/NNN-.../` directory.

### Other short-lived branches

Use when the change is **not** tracked as a Spec Kit feature under `specs/`, or is an urgent
production fix:

| Prefix | Use when | Base from | PR into |
|--------|----------|-----------|---------|
| `feat/<slug>` | Product/behavior change **without** a Spec Kit `specs/NNN-...` feature | `master-dev` | `master-dev` |
| `fix/<slug>` | Bug fix for test line | `master-dev` | `master-dev` |
| `hotfix/<slug>` | Urgent production fix | `master` | `master`, then **back-merge** to `master-dev` |
| `docs/<slug>` | Documentation-only | `master-dev` | `master-dev` |
| `chore/<slug>` | Tooling, deps, CI plumbing with no product behavior | `master-dev` | `master-dev` |
| `refactor/<slug>` | Internal restructure with no intended behavior change | `master-dev` | `master-dev` |

Examples: `feat/layered-compose-deploy`, `fix/api-readiness-timeout`,
`hotfix/migrate-approval-bypass`, `docs/local-environment-runbook`,
`chore/uv-lock-refresh`.

### Forbidden

- Environment or deploy-line names: `test`, `prod`, `local`, `staging`, `dev` as the
  whole branch name (or as a false long-lived line).
- Alternate long-lived lines: `main`, `develop`, `release/*` (unless a future contract
  replaces this standard).
- Spec feature with a non-matching branch: work tracked as `specs/004-foo/` **must** use
  branch `004-foo`, not `feat/foo`, `feature/foo`, or `004_foo`.
- Numbered `NNN-...` branches that do not match an existing `specs/NNN-.../` directory.
- Encoding secrets, hostnames, or customer data in the branch name.

### Development flow

1. Branch from `master-dev` (or from `master` only for `hotfix/*`).
2. Open a PR into the table target above; `quality-gate` must pass.
3. After test-environment validation, open a promotion PR from `master-dev` into `master`.
4. Hotfixes that land on `master` MUST be back-merged into `master-dev`.

Environment selection for `make migrate` and `make deploy` / `make deploy-down` is **not**
inferred from the branch. Use explicit `mode=local|test|prod` (and production approval for
`prod`) per `shared/contracts/repository-workflow/v1/environment-mode.md`. Future CD jobs may
be *scheduled* from `master-dev` / `master` while still passing explicit `mode=` on the
command line.

### Layered Compose (ADR 003)

| Command | Environment | What runs |
|---------|-------------|-----------|
| `make dev` / `make dev-down` | local only | Middleware containers; apps stay host processes |
| `make build` | any | Five service images + asset bundles |
| `make deploy` / `make deploy-down` | test or prod only | Middleware + app containers on the shared host |
| `make migrate` | local / test / prod | Reviewed Alembic only; never starts containers |

See [`deploy.md`](deploy.md) and `docs/decisions/003-layered-compose-deploy.md`.

## Local configuration

1. Copy `.env.example` to `.env.local`.
2. Replace synthetic placeholders with local values.
3. Never commit `.env.local` or any file containing real credentials.

## Secret discovery

If a real secret is found in Git history or build output:

1. Revoke/rotate the credential immediately.
2. Audit usage via provider logs.
3. Open a tracked remediation issue with owner, approver and expiry.
4. Only after audit, consider minimal approved history remediation.

### Exception format

Every security exception must be recorded with:

| Field | Example |
|-------|---------|
| Owner | security-oncall@tokenmarket.local |
| Approver | eng-lead@tokenmarket.local |
| Issue | PROJ-1234 |
| Expiry | 2026-08-15 |
| Reason | transient allow-list for integration test fixture |

Exceptions are not substitutes for rotation; they must have a fixed expiry and
be reviewed before renewal.

## CI recovery

- Keep the required job name `quality-gate` stable through rollbacks.
- Suspected cache contamination: bump cache key or disable cache.
- Failed `master` or `master-dev` merge: open a review-revert PR; never force-push.

### Runner or scanner failure

If `quality-gate` fails because a hosted tool or scanner is unavailable:

1. Check `ops/workflow/toolchains.json` for the pinned version/SHA.
2. Confirm the failure reproduces locally with `make ci`.
3. If the scanner is missing only on the runner, install it via the CI workflow
   using the same pinned reference; do not downgrade or skip the step.
4. Record the incident and the resolution in this runbook.

### Required check rollout order

1. Merge the CI workflow and verify at least one successful PR `quality-gate` run.
2. Enable the `quality-gate` required status check in branch protection/rulesets for
   both `master` and `master-dev`.
3. Enable "Do not allow bypassing the above settings" for each ruleset.
4. Enable "Restrict pushes that create files" and "Require a pull request before merging".

### GitHub ruleset configuration

Configure repository rulesets for the long-lived branches:

#### `master` (production)

- **Target branches**: `master`
- **Bypass list**: empty (no role, team, or app may bypass)
- **Restrictions**: disable direct push and force push
- **Pull request**: required, at least 1 reviewer, dismiss stale approvals on new commits
- **Required status checks**: `quality-gate`
- **Commit message**: do not require signed commits unless a later ADR adopts them
- **Promotion**: prefer PRs that merge `master-dev` → `master` after test validation

#### `master-dev` (test deployment)

- **Target branches**: `master-dev`
- **Bypass list**: empty
- **Restrictions**: disable direct push and force push
- **Pull request**: required, at least 1 reviewer, dismiss stale approvals on new commits
- **Required status checks**: `quality-gate`

### Linking PR and final long-lived-branch runs

Each PR must show a green `quality-gate` run before merge. After merge, the
`push` trigger on `master` or `master-dev` produces the final run for that tip.
Incident response and release evidence must reference both the PR run ID and the
final long-lived-branch run ID (and for production, the promotion PR into `master`).
