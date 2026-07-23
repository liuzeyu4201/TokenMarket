# Implementation Plan: 用户注册与初始界面

**Branch**: `003-user-registration-ui` | **Date**: 2026-07-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-user-registration-ui/spec.md`

## Summary

Deliver SF03 **user registration** as the first business capability on API Service, plus a **minimal React shell** so a visitor can navigate from a home placeholder to a registration page, submit phone/nickname/role, and see success or structured failures—without issuing sessions (SF04).

Technical approach (see [research.md](./research.md)): contract-first OpenAPI under this feature (promoted to `shared/contracts/user-registration/v1/` at implement); PostgreSQL `users` + `registration_idempotency_records` owned by API Service with Alembic expand/backout; CN mobile normalization pure function; Redis fixed-window rate limits (IP + phone) fail-closed if Redis is down; unified envelope `{code,message,data,request_id,timestamp}`; frontend React Router shell (`/`, `/register`, `*`) with form UX and no auth store.

## Technical Context

**Language/Version**: Python 3.11.15 (API Service); TypeScript strict / React 18 / Node 24.18.0 (frontend); PostgreSQL 15.x; Redis 7.x

**Primary Dependencies**: FastAPI + SQLAlchemy asyncio + asyncpg + Alembic + Pydantic v2 (existing api-service locks + reviewed Redis client addition); React 18 + Vite + Vitest + Testing Library + React Router (frontend lock addition); no Gateway business change

**Storage**: PostgreSQL is system of record for users and registration idempotency (24h window). Redis holds ephemeral registration rate-limit counters only.

**Testing**: pytest / pytest-asyncio / httpx (API unit, integration with real PG, concurrency, migration upgrade/downgrade, privacy redaction, rate-limit); Vitest + Testing Library (routes, form states, error mapping); contract tests for OpenAPI/schema assets; ≥80% line coverage on changed user-domain packages

**Target Platform**: Local developer hosts (macOS arm64 / Linux x86_64) with API Service as host process, frontend Vite dev server, SF02 local PG/Redis when available; production image path unchanged except new migration and app code

**Project Type**: Polyglot monorepo feature — Python domain API + React SPA shell + versioned HTTP contracts + Alembic migration

**Performance Goals**: p95 register ≤ 500ms in normal local integration (no SMS; automated or env-gated microbench); registration UI interactive ≤ 3s on typical dev machine **via manual quickstart/README acceptance** (not a flaky CI hard gate); 100 concurrent same-phone registrations → ≤1 user row

**Constraints**: No tokens/sessions; no password/email/SMS; no Gateway registration proxy; no business services in Compose; soft-deleted phones not recreated; PII redaction in logs/metrics/UI; rate-limit defaults IP 20/15m and phone 5/15m; idempotency 24h; root path is shell home not register form

**Scale/Scope**: Single registration endpoint; two durable tables; one Redis key namespace; three frontend routes; one OpenAPI contract package; V0.1 identity foundation only

**Affected Components**:

| Component | Change |
|-----------|--------|
| `services/api-service/` | User domain, register route, schemas, repos, rate limit, migration, metrics, tests |
| `frontend/` | Router shell, home/register/not-found, API client, form, tests |
| `shared/contracts/user-registration/v1/` | Promote OpenAPI + code/normalization docs (implement) |
| `docs/api/` | Index link to registration contract |
| `specs/003-user-registration-ui/contracts/` | Design-time source of truth (this plan phase) |
| `proxy-gateway/`, `billing-service/`, `admin-service/` | **No** functional change |

**Contracts**: [contracts/user-registration.openapi.yaml](./contracts/user-registration.openapi.yaml), [business-codes.md](./contracts/business-codes.md), [phone-normalization.md](./contracts/phone-normalization.md). Additive new major surface `user-registration/v1`; does not mutate health or workflow contracts.

**Data & Migrations**: See [data-model.md](./data-model.md). Alembic revision after `0001_baseline`; short transaction for user+idempotency; unique phone including soft-deleted; downgrade documented; startup must not auto-migrate. **Backup/retention/restore**: `users` and `registration_idempotency_records` inherit the API Service PostgreSQL instance’s existing platform backup and non-prod restore procedures; this feature does not add a separate backup job. Soft-delete is a business state, not restore. Account hard-delete, point-in-time user restore, and product “account recovery” remain out of scope. Idempotency rows are 24h auxiliary data (loss only drops replay, not account truth).

**Security & Privacy**: Phone PII; mask in responses/logs; synthetic fixtures only; reject client-supplied id/status; rate limit dual dimension (IP always; phone only after successful normalize); unified `RATE_LIMITED` envelope that does not vary by registered/soft-deleted state (no enumeration side channel); Redis fail-closed for register; no secrets in URLs; CORS/local origins only as needed for Vite→API (config, not hardcode prod).

**Observability & Reliability**: `X-Request-ID` correlation; registration attempt counters/histograms without high-cardinality phone labels; 503 on DB/Redis outage; client retries with same idempotency key within 24h. **Frontend HTTP**: single register request timeout **10s**; **no automatic retry** of register POST; user-initiated retry reuses the same `Idempotency-Key` until success, expiry, or a new independent submit. **Alerts (required)**: ship Prometheus alert rules for registration (elevated 5xx/`SERVICE_UNAVAILABLE`, rate-limit backend unavailable, anomalous failure rate) with severity, owner = API Service, and a runbook under `ops/` describing detection signals, triage steps, and recovery; alerts/logs remain PII-redacted (no full phone).

**Deployment & Rollback**: Ship migration before or with API image that requires new tables; rollback = disable route/traffic → downgrade migration if safe → previous image; frontend independent static deploy; no ADR required for first domain tables inside existing API Service boundary (no new service).

## Constitution Check

*GATE: MUST pass before Phase 0 research and MUST be re-checked after Phase 1 design.*

### Pre-Research Gate

| Gate | Status | Evidence / Decision |
|------|--------|---------------------|
| Architecture and ownership | PASS | API Service owns user domain + DB; frontend presentation only; no cross-service storage; no new microservice |
| Contracts and compatibility | PASS | OpenAPI + business codes + phone normalization defined before implement; envelope versioned |
| Security and privacy | PASS | No passwords/tokens; PII redaction; rate limit; soft-delete no silent replace; synthetic test data |
| Data correctness | PASS | PG source of truth; unique phone; idempotency durable 24h; short txn; Alembic only |
| Testing | PASS | Unit/integration/concurrency/migration/privacy/rate-limit/UI tests planned; TDD |
| Operations | PASS | Metrics + request_id; 503 fail-closed; no pager design beyond existing service metrics ownership |
| Delivery | PASS | Lockfile-reviewed deps; CI via existing make test/lint; traceability via quickstart |

No constitution waiver required. (Weekly Spec plaintext password clause is **rejected** by constitution and by this feature scope.)

### Post-Design Gate

| Gate | Status | Phase 1 evidence |
|------|--------|------------------|
| Architecture and ownership | PASS | [data-model.md](./data-model.md) ownership; research Decision 1 |
| Contracts and compatibility | PASS | [contracts/](./contracts/) OpenAPI + codes + normalization |
| Security and privacy | PASS | Codes privacy rules; rate-limit fail-closed; mask rules in research Decision 10 |
| Data correctness | PASS | Tables, invariants, concurrency mapping, 24h idempotency |
| Testing | PASS | [quickstart.md](./quickstart.md) validation matrix |
| Operations | PASS | Metrics/logging and 503 paths in research + quickstart |
| Delivery | PASS | Migration/rollback sketch; component list; promote contracts path |

Post-design result: **PASS** — no unresolved product clarification; implementation may proceed to `/speckit-tasks`.

## Project Structure

### Documentation (this feature)

```text
specs/003-user-registration-ui/
├── spec.md
├── plan.md                 # This file
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── user-registration.openapi.yaml
│   ├── business-codes.md
│   └── phone-normalization.md
└── tasks.md                # /speckit-tasks (not this command)
```

### Source Code (repository root) — target layout at implement

```text
services/api-service/
├── alembic/versions/0002_*.py          # users + idempotency
├── app/
│   ├── main.py                         # mount router
│   ├── schemas/                        # envelope, register DTOs
│   ├── domain/users/                   # normalize, service rules
│   ├── repositories/                   # user + idempotency
│   ├── api/v1/auth.py                  # POST /api/v1/auth/register
│   ├── rate_limit.py                   # Redis fixed window
│   └── observability.py                # registration metrics
└── tests/
    ├── unit/
    ├── integration/
    └── test_register_*.py

frontend/src/
├── main.tsx
├── App.tsx                             # Router provider
├── layouts/AppShell.tsx
├── pages/Home.tsx
├── pages/Register.tsx
├── pages/NotFound.tsx
├── api/client.ts
├── api/v1/auth.ts
├── types/auth.ts
└── styles/…                            # minimal CSS

shared/contracts/user-registration/v1/  # promoted copies at implement
docs/api/README.md                      # index entry
```

**Structure Decision**: Keep domain logic inside existing `api-service` package boundaries (handlers → domain → repository). Frontend grows toward the documented `pages/` / `api/` layout without pulling full marketplace UI. Contracts are authored in the feature directory then promoted to `shared/contracts` so CI contract validation can own a stable path.

## Complexity Tracking

> No constitution violations requiring waiver.

| Violation | Why Needed | Simpler Alternative Rejected | ADR / Owner | Controls | Review or Expiry |
|-----------|------------|-----------------------------|-------------|----------|------------------|
| — | — | — | — | — | — |

## Phase 0 & 1 Outputs

| Artifact | Path |
|----------|------|
| Research | [research.md](./research.md) |
| Data model | [data-model.md](./data-model.md) |
| Contracts | [contracts/](./contracts/) |
| Quickstart | [quickstart.md](./quickstart.md) |

## Agent context

No `.specify` agent-context update script is present in this repository; active feature pointer remains `.specify/feature.json` → `specs/003-user-registration-ui`. Implementers should follow `CLAUDE.md` / constitution and this plan.

## Next command

```text
/speckit-tasks
```
