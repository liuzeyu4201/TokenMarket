# Workflow Runbook

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
- Failed main merge: open a review-revert PR; never force-push.

### Runner or scanner failure

If `quality-gate` fails because a hosted tool or scanner is unavailable:

1. Check `ops/workflow/toolchains.json` for the pinned version/SHA.
2. Confirm the failure reproduces locally with `make ci`.
3. If the scanner is missing only on the runner, install it via the CI workflow
   using the same pinned reference; do not downgrade or skip the step.
4. Record the incident and the resolution in this runbook.

### Required check rollout order

1. Merge the CI workflow and verify at least one successful PR `quality-gate` run.
2. Enable the `quality-gate` required status check in branch protection/ruleset.
3. Enable "Do not allow bypassing the above settings" for the ruleset.
4. Enable "Restrict pushes that create files" and "Require a pull request before merging".

### GitHub ruleset configuration

Configure the repository ruleset for `main` with:

- **Target branches**: `main`
- **Bypass list**: empty (no role, team, or app may bypass)
- **Restrictions**: disable direct push and force push
- **Pull request**: required, at least 1 reviewer, dismiss stale approvals on new commits
- **Required status checks**: `quality-gate`
- **Commit message**: do not require signed commits unless ADR-002 is adopted

### Linking PR and final-main runs

Each PR must show a green `quality-gate` run before merge. After merge, the
`push` trigger on `main` produces the final-main run. Incident response and
release evidence must reference both the PR run ID and the final-main run ID.

