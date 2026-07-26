# Runbook: Phone authentication & session (API Service)

**Owner**: API Service authentication on-call  
**Feature**: `004-phone-login-session-ui` / SF04  
**Alerts**: `ops/alerts/authentication.yml`  
**Schedule**: `ops/schedules/authentication-cleanup.yml`  
**PII**: Never log or paste full phone numbers, OTP codes, session cookies, CSRF
tokens, or raw key material. Use `request_id`, challenge/session references, and
masked forms only.

## Scope

Covers verification-code request/verify, SMS delivery dispatcher, browser
session cookie lifecycle, CSRF/Origin enforcement, rate limiting, and
authentication retention cleanup.

## Signals

| Signal | Warning | Critical |
|--------|---------|----------|
| Auth readiness | — | Continuous 5m unavailable |
| Server/dependency failure ratio | 10m >5% and ≥100 eligible | 5m >20% and ≥50 eligible |
| Provider rejected/timeout/unknown | 10m >10% and ≥50 dispatch | 5m >25% and ≥25 dispatch |
| Oldest eligible dispatcher work | >30s for 5m | >120s for 5m |
| Session revocation visibility p95 | — | 5m >1s and ≥20 samples |
| Cleanup command | Single failure or last-success >2h | 3 consecutive failures, last-success >4h, or material past 24h hard deadline |
| Cleanup due backlog oldest age | >1h | >2h |
| Redis rate-limit backend | — | Any unavailability spike (challenge fail-closed) |

User field validation errors, incorrect OTP attempts, and normal rate-limit
rejections **do not** count toward server/dependency failure ratio.

Recovery for every alert requires **two consecutive evaluation windows** below
threshold before auto-resolve.

## Diagnosis tree

### 1. Capture context (no secrets)

1. Alert name, severity, firing time range.
2. Sample `request_id` / challenge reference / session reference (opaque only).
3. API Service `/health/live`, auth readiness, and `/metrics` snapshot.

### 2. Database (PostgreSQL)

- Symptoms: readiness down, verify/session 503, cleanup errors.
- Check: connectivity, pool saturation, slow queries on
  `verification_challenges`, `auth_sessions`, indexes.
- Action: restore connectivity; do **not** run schema mutation from app startup.
- Migrations: see `ops/runbooks/migrations.md` (0003 order, backout).

### 3. Redis

- Symptoms: challenge request fail-closed; `tokenmarket_rate_limit_backend_unavailable_total`.
- Existing sessions still validate against PostgreSQL (session path is not Redis).
- Action: restore Redis; no rate-limit key migration required.

### 4. SMS provider / dispatcher

- Symptoms: provider rejected/timeout/unknown ratios; dispatcher queue age.
- Check:
  - Dispatcher process/liveness and lease claim metrics
    (`tokenmarket_auth_dispatcher_claims_total`,
    `tokenmarket_auth_dispatcher_queue_age_seconds`).
  - Provider adapter configuration (approved adapter in test/prod; synthetic only local).
  - Pending vs dispatching challenges; `send_started_at` recovery path (query-or-invalidate, never auto-resend).
- Action: fix provider credentials/network; scale or restart dispatcher; allow
  graceful stop to finish in-flight work without claiming new leases.

### 5. Cleanup backlog

- Symptoms: cleanup last-success age, due backlog, hard-deadline breach.
- Stable entrypoint (test/prod schedule and local manual):

```bash
uv run --project services/api-service --locked \
  python -m app.maintenance.auth_cleanup \
  --batch-size 500 \
  --max-runtime-seconds 900
```

- Schedule: UTC `17 * * * *` (see `ops/schedules/authentication-cleanup.yml`).
- Concurrent runs: advisory lock; second instance exits `already_running` (success).
- Retention: challenge/OTP `expires_at+22h`, idempotency `created_at+22h`,
  sessions 90d after expire/revoke, security events 180d.
- Action: run the entrypoint once against the environment DATABASE_URL; inspect
  desensitized JSON outcome (`rows_by_entity`, `oldest_due_age_seconds`).
- Do **not** add a public Make action, second wrapper, or startup cleanup loop.

### 6. CSRF / Origin / trusted proxy

- Elevated `tokenmarket_auth_csrf_rejected_total`.
- Check browser origin allowlist, trusted proxy CIDRs, Cookie flags on HTTPS.

## Rollback (keep data)

Preferred production rollback is **application-only** and **keeps additive data**:

1. Disable authentication traffic at the edge or feature flag (fail closed).
2. Roll back API Service and Frontend images to the last known good digests.
3. Leave authentication tables (`verification_*`, `auth_sessions`,
   `authentication_security_events`) intact; previous app versions ignore them.
4. Keep security events for audit; do not truncate.
5. Confirm cleanup schedule still targets the rolled-back same-version image or
   pause the schedule until the next forward deploy.

### Destructive downgrade (last resort)

Only after explicit approval:

1. Auth traffic disabled and Cookie expiry window accounted for.
2. All sessions revoked.
3. Security audit retention/export decision approved.
4. Isolated PostgreSQL 15 **backup → restore** evidence recorded (head restoration
   is **not** a data restore).
5. Then reverse migration order per `ops/runbooks/migrations.md` (0003 drop order:
   events → sessions → challenges → idempotency).

## Related

- Migrations: `ops/runbooks/migrations.md`
- Registration (adjacent surface): `ops/runbooks/registration.md`
- Deploy: `ops/runbooks/deploy.md`

## SMS adapter readiness matrix (FR-016)

| Mode | `AUTH_SMS_ADAPTER` | Runtime adapter | Auth readiness |
|------|--------------------|-----------------|----------------|
| local | `synthetic` / empty | `SyntheticSmsAdapter` | allowed (dev only) |
| test / prod | `synthetic` / `fake` / empty | `ProductionBlockedSmsAdapter` | **fail closed** |
| test / prod | any non-approved name | `ProductionBlockedSmsAdapter` | **fail closed** until a real approved adapter is implemented and configured |
| any | injected test override | test fake | tests only |

Production must never become usable via silent fallback to synthetic codes.
Procurement of a real provider requires a reviewed adapter implementation,
readiness checks (`AUTH_TLS_READY`, keys, trusted proxies/origins), and
release candidate evidence before activation.

## Live backup → restore gate (SC-011 / T133)

Isolated restore verification uses:

```bash
export AUTH_BACKUP_TEST_DATABASE_URL='postgresql://…@127.0.0.1:…/tokenmarket_auth_restore'
# Requires Docker when the optional live pytest path is enabled.
uv run --project tools/workflow --locked python -m pytest \
  tests/workflow/test_auth_backup_restore.py -q
```

Never point the live gate at a shared developer or production DSN. Manifests
are redacted (no passwords, phones, OTP, cookies, or keys).
