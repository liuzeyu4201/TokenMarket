# Quickstart Validation: 用户注册与初始界面

**Feature**: `003-user-registration-ui`  
**Purpose**: Post-implementation acceptance guide; automated tests remain authoritative for concurrency, migration, and rate-limit edge cases  
**Safety**: Use only synthetic phones and local credentials. Never point at test/production data stores outside the developer workspace.

## 0. Prerequisites

- Feature branch `003-user-registration-ui` checked out.
- Toolchain: Go/Python/Node versions per repository pins.
- Local PostgreSQL and Redis available (SF02 `make dev` when activated, or equivalent isolated test containers used by CI fixtures).
- API Service `DATABASE_URL` and Redis URL configured for **local** only.
- Contracts readable at [contracts/](./contracts/).

## 1. Quality gates (repository)

From repo root:

```bash
make lint
make test
```

Expected:

- API user-domain packages meet coverage policy (≥80% on changed domain code).
- Frontend type-check, lint, and Vitest pass.
- No contract asset validation failures for `user-registration/v1` once promoted.

## 2. Schema migration

```bash
cd services/api-service
# apply reviewed revision that creates users + registration_idempotency_records
make migrate   # or project-standard alembic upgrade head via root make migrate
```

Expected:

- Upgrade succeeds on empty DB after baseline.
- Downgrade path removes new tables/types without error (run in disposable DB only).

## 3. API happy path

Start API Service per service README (host process). Then:

```bash
REQ=req-$(uuidgen)
KEY=idem-$(uuidgen)
curl -sS -X POST "http://127.0.0.1:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $KEY" \
  -H "X-Request-ID: $REQ" \
  -d '{"phone":"+86 138 0013 8000","nickname":"验收用户","role":"buyer"}'
```

Expected:

- HTTP 200, `code` = `"0"`.
- `data.user_id` UUID, `data.role` = `buyer`, `data.status` = `active`, `created_at` present.
- No full phone in body; optional `phone_masked` only.
- Response and logs include `request_id`; logs must not contain `13800138000` in full.

Replay same key and body → same `user_id`, still one DB row.

## 4. Negative API cases (manual or test suite)

| Case | Expect |
|------|--------|
| Second registration, new key, same phone | `PHONE_ALREADY_REGISTERED`, HTTP 409, still one user |
| Soft-deleted user same phone (fixture) | `ACCOUNT_UNAVAILABLE`, distinct from occupied |
| Invalid phone / nickname / role | `VALIDATION_ERROR` with field errors |
| Same key, different nickname | `IDEMPOTENCY_KEY_CONFLICT` |
| Expired key (>24h; clock fixture in tests) | `IDEMPOTENCY_KEY_EXPIRED` |
| Burst >20/IP or >5/phone in 15m | `RATE_LIMITED`, HTTP 429, no new users |
| DB down | `SERVICE_UNAVAILABLE` / 503, no partial user |
| Redis down | 503 fail-closed on register (no unlimited writes) |

## 5. Concurrency spot-check

Prefer automated test: 100 parallel POSTs same normalized phone, distinct keys → exactly one `users` row; others conflict/limit.

## 6. Frontend shell

```bash
cd frontend
make bootstrap   # if required
npm run dev
```

Browser checks:

1. Open `/` → home **placeholder** shell, **not** the registration form; nav link to Register visible.
2. **First-paint interactivity (ER-004)**: From a normal cold `npm run dev`, open `/register` on a typical dev machine; within **3 seconds** the phone/nickname/role fields and submit control should be usable (focusable/typeable). Record pass/fail in your notes—this is **manual** acceptance, not a CI gate.
3. Open `/register` → phone, nickname, role, submit.
4. Submit valid synthetic phone → success confirmation with user id + role; copy states **not logged in**.
5. Submit invalid fields → field-level errors.
6. Submit duplicate phone → neutral occupied message (no other account PII).
7. Open unknown path → not-found/placeholder with link home or register.
8. Keyboard-only can complete the form.

Automated: `npm test` covers route render and primary form states.

## 7. End-to-end local path (SC-006)

With API + frontend + DB + Redis up:

1. From `/`, navigate to Register within UI.
2. Complete registration under 2 minutes.
3. Confirm success UI and single DB row.

## 8. Privacy scan

```bash
# example: scan recent API logs / test artifacts for raw fixture phones
# must find only masked forms or no match
```

CI/security tests should fail if full mobile patterns appear in registration log fields or error bodies.

## 9. Rollback drill (non-prod)

1. Stop accepting register traffic.
2. Deploy previous API image **or** disable route.
3. On disposable DB only: `alembic downgrade` one revision; confirm tables gone.
4. Frontend rollback is independent static asset revert.

## Traceability (spec → proof)

| Success criteria | Primary proof |
|------------------|---------------|
| SC-001 / SC-002 | Integration + concurrency tests |
| SC-003 | Idempotency unit/integration + expiry fixture |
| SC-004 | Timing assertion or load microbench in integration |
| SC-005 | Log/response redaction tests |
| SC-006 | Manual quickstart §7 or e2e script |
| SC-007 | API + UI error mapping tests |
| SC-008 | Frontend route tests |
| SC-009 | Rate-limit integration tests |
