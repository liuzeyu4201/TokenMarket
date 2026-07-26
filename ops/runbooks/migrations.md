# Migration Runbook

## Owner order

Apply (and verify) owners strictly in this order:

1. `api-service`
2. `billing-service`

Manifest: `ops/migrations/owners.json`. Non-owners (for example `admin-service`)
must not own schema.

Public workflow: `make migrate mode=local|test|prod` (root Makefile only).
Never auto-migrate on application startup.

## API Service revision chain (phone auth)

| Revision | Purpose |
|----------|---------|
| `0001_baseline` | Baseline scaffold |
| `0002_users_registration` | Users + registration idempotency |
| `0003_phone_login_session` | Phone login challenges, sessions, security events |

### `0003_phone_login_session` forward order

Additive only (varchar + CHECK, no new PostgreSQL enum types for auth states):

1. Create `verification_request_idempotency_records` and indexes.
2. Create `verification_challenges` with FK to users/idempotency; dispatch
   owner/lease/`send_started_at`/finalize columns and pending/dispatching indexes.
3. Create `auth_sessions` and partial unique active-session constraint.
4. Create `authentication_security_events` with nullable `ON DELETE SET NULL`
   audit FKs to users/challenges/sessions.
5. Add cleanup/query indexes (`delete_after`, etc.).

Upgrade path is repeat-safe through Alembic versioning (not custom
`IF NOT EXISTS` schema mutation).

### `0003` backout / downgrade order

Preferred production rollback leaves additive tables intact; older app images
ignore them. Prefer application rollback over schema downgrade.

When a true downgrade is required, drop in reverse FK order:

1. `authentication_security_events` (indexes then table)
2. `auth_sessions`
3. `verification_challenges`
4. `verification_request_idempotency_records`

### Destructive downgrade approval

Destructive downgrade of `0003` deletes authentication and audit data. It is
only allowed after **all** of the following:

1. Authentication traffic disabled at the edge / feature flag.
2. All sessions revoked and Cookie expiry window accounted for.
3. Security audit retention/export decision approved in writing.
4. Event FK dependencies removed only via the reverse order above.
5. Isolated PostgreSQL 15 **backup → fresh restore** evidence recorded for
   pending/dispatching/delivered/consumed challenges, active/revoked sessions,
   and security events (opaque IDs/counts only in evidence).

**Head restoration is not data restore.** CI `migrate-integration-check`
proves forward → backout → retry → restore head sequencing on pinned PostgreSQL
15; it does **not** prove business-data recoverability. Real backup/restore
evidence is required before any destructive production claim.

## Backout (operator steps)

Each owner migration includes a downgrade path. To back out:

1. Identify the last applied revision (`alembic current` / migration checker).
2. Run `make migrate mode=<env>` toward the target revision, or downgrade via
   Alembic under the component lockfile.
3. Never edit an already applied migration file.
4. For `0003`, prefer app rollback; if schema reverse is required, complete the
   destructive downgrade approval checklist first.

## Rollback (production)

For production, use the same `mode=prod` plus approved production confirmation.
After schema operations, re-check API-then-Billing head alignment and auth
readiness before re-enabling traffic.

## CI evidence

- `make migrate-check` — pending/owner graph validation without mutating shared DB.
- `make migrate-integration-check` — isolated PostgreSQL 15 container,
  API-then-Billing forward/backout/retry/head restoration.
