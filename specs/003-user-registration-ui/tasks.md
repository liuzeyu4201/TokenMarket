# Tasks: 用户注册与初始界面

**Input**: Design documents from `/specs/003-user-registration-ui/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Tests are REQUIRED for every behavior change and MUST be written and observed failing before the corresponding implementation task. Domain packages under `services/api-service/app/domain/` and registration handlers require ≥80% line coverage plus direct negative coverage for uniqueness, idempotency, concurrency, rate limit, and PII redaction.

**Organization**: Tasks are grouped by user story (US1–US3). Setup and Foundational block all stories. MVP = Phase 1–3 (US1 end-to-end register via UI + API happy path). US2 hardens safety; US3 completes shell/a11y polish beyond the minimal nav needed for US1.

**UI shell boundary (analyze I2 / option A)**:

- **US1 owns** minimal navigable shell required for the happy path: `AppShell` with Home + Register links, `Home` placeholder (not the form), `/` and `/register` routes, Register form + success. Do **not** implement catch-all `*`, full a11y polish, or narrow-viewport CSS in US1 unless required for basic usability.
- **US3 owns** NotFound / 暂未开放 (`*`), semantic a11y refinements, responsive CSS so submit stays visible, and `frontend/README.md` route notes. US3 may edit the same files as US1 but only for those deltas—avoid re-implementing Home/Register from scratch.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks in the same batch)
- **[Story]**: Maps to User Story 1/2/3 from `spec.md` (`[US1]`, `[US2]`, `[US3]`)
- Every task names the exact file path(s) it creates or changes

## Path Conventions

- API: `services/api-service/`
- Frontend: `frontend/`
- Shared contracts: `shared/contracts/user-registration/v1/`
- Feature contracts (source): `specs/003-user-registration-ui/contracts/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Materialize contracts, lock reviewed dependencies, and scaffold package directories without business behavior yet.

- [x] T001 Promote feature contracts into versioned shared path by copying `specs/003-user-registration-ui/contracts/user-registration.openapi.yaml`, `business-codes.md`, and `phone-normalization.md` to `shared/contracts/user-registration/v1/` and register ownership/version in `shared/contracts/README.md`
- [x] T002 [P] Index the registration contract from `docs/api/README.md` with a link to `shared/contracts/user-registration/v1/`
- [x] T003 Add reviewed Redis async client dependency to `services/api-service/pyproject.toml` and refresh `services/api-service/uv.lock` without changing unrelated pins
- [x] T004 [P] Add `react-router-dom` (and types if needed) to `frontend/package.json` and refresh `frontend/package-lock.json`
- [x] T005 [P] Create API package skeletons (empty modules / `__init__.py` only) under `services/api-service/app/schemas/`, `services/api-service/app/domain/users/`, `services/api-service/app/repositories/`, `services/api-service/app/api/v1/`
- [x] T006 [P] Create frontend package skeletons under `frontend/src/layouts/`, `frontend/src/pages/`, `frontend/src/api/`, `frontend/src/api/v1/`, `frontend/src/types/`, `frontend/src/styles/`
- [x] T007 [P] Add contract-asset presence/schema smoke tests for `user-registration/v1` in `shared/tests/test_contract_assets.py` (or extend existing validator coverage)

**Checkpoint**: Contracts are discoverable; deps locked; empty packages exist; no registration behavior yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared envelope, persistence session, migration, Redis wiring, and test factories required by all stories.

**CRITICAL**: No user-story implementation begins until this phase passes. Write foundational tests first and observe them fail where they assert missing behavior.

- [x] T008 [P] Add failing tests for unified API envelope models (`code`, `message`, `data`, `request_id`, `timestamp`) in `services/api-service/tests/unit/test_envelope_schemas.py`
- [x] T009 [P] Add failing migration tests for upgrade/downgrade of users + registration_idempotency tables in `services/api-service/tests/integration/test_users_migration.py`
- [x] T010 [P] Add failing unit tests for CN phone normalization matrix from `contracts/phone-normalization.md` in `services/api-service/tests/unit/test_phone_normalization.py`
- [x] T011 Implement `BaseResponse` / error envelope Pydantic models in `services/api-service/app/schemas/envelope.py` until T008 passes
- [x] T012 Implement `normalize_cn_mobile` pure function and validation errors in `services/api-service/app/domain/users/phone.py` until T010 passes
- [x] T013 Add Alembic revision creating ENUM `user_role`/`user_status`, table `users`, table `registration_idempotency_records`, uniques/checks/FKs in `services/api-service/alembic/versions/0002_users_registration.py` until T009 passes
- [x] T014 Implement SQLAlchemy models for User and RegistrationIdempotencyRecord in `services/api-service/app/domain/users/models.py` matching `data-model.md`
- [x] T015 Implement async session dependency factory (app-scoped engine reuse, request-scoped session) in `services/api-service/app/dependencies.py` and wire lifespan if needed in `services/api-service/app/main.py` without auto-migrate on startup
- [x] T016 [P] Implement Redis client configuration and fail-closed helper stubs in `services/api-service/app/rate_limit.py` and document `REDIS_URL` placeholder in `.env.example`
- [x] T017 [P] Extend registration metrics helpers (attempt totals, duration histogram, rate-limit counters; no phone labels) in `services/api-service/app/observability.py`
- [x] T018 Establish integration fixtures: disposable PG schema, synthetic phones, idempotency key factory, optional Redis fake/real toggle in `services/api-service/tests/conftest.py`
- [x] T019 [P] Add frontend env placeholder for API base URL (e.g. `VITE_API_BASE_URL`) in `frontend/.env.development` example or documented `.env.example` under `frontend/` without committing secrets

**Checkpoint**: Migration applies/rolls back; envelope + phone normalize tested; sessions/Redis/metrics hooks exist; stories can start.

---

## Phase 3: User Story 1 - 通过界面完成首次注册 (Priority: P1) 🎯 MVP

**Goal**: Unauthenticated visitor can reach register from the app shell, submit valid phone/nickname/role, create one active user, and see a success confirmation (no token/session).

**Independent Test**: Start API (migrated) + frontend; from `/` navigate to `/register`; submit unused CN mobile + nickname + role; UI shows user_id/role success and “not logged in”; DB has exactly one matching `users` row with audit fields.

### Tests for User Story 1 (write and observe failing first)

- [x] T020 [P] [US1] Add unit tests for request hash canonicalization and nickname validation rules in `services/api-service/tests/unit/test_registration_validation.py`
- [x] T021 [P] [US1] Add repository/service unit tests for happy-path create user + idempotency row in one transaction in `services/api-service/tests/unit/test_registration_service.py`
- [x] T022 [P] [US1] Add HTTP contract/integration test for `POST /api/v1/auth/register` success envelope and headers in `services/api-service/tests/integration/test_register_api.py`
- [x] T023 [P] [US1] Add privacy tests that success body/logs never contain full phone plaintext in `services/api-service/tests/unit/test_registration_privacy.py`
- [x] T024 [P] [US1] Add frontend tests for register form render, client required-field hints, success state, API client parsing of `code=0`, and **10s timeout / no auto-retry** behavior in `frontend/src/pages/Register.test.tsx` and `frontend/src/api/v1/auth.test.ts`
- [x] T025 [P] [US1] Add frontend smoke tests that `/` is not the register form and exposes a Register nav/link in `frontend/src/App.test.tsx` (or `frontend/src/pages/Home.test.tsx`)

### Implementation for User Story 1

- [x] T026 [P] [US1] Implement register request/response DTOs aligned with OpenAPI in `services/api-service/app/schemas/register.py`
- [x] T027 [P] [US1] Implement user and idempotency repositories in `services/api-service/app/repositories/users.py` and `services/api-service/app/repositories/idempotency.py`
- [x] T028 [US1] Implement `RegistrationService.register` happy path (normalize → insert user active → insert idempotency 24h → commit) in `services/api-service/app/domain/users/service.py`
- [x] T029 [US1] Implement `POST /api/v1/auth/register` router with `Idempotency-Key` requirement, envelope mapping, and no token issuance in `services/api-service/app/api/v1/auth.py`
- [x] T030 [US1] Mount v1 auth router and ensure CORS for local Vite origin is configurable in `services/api-service/app/main.py`
- [x] T031 [P] [US1] Implement typed API client + `registerUser` with **10s request timeout**, **no automatic retry** on register POST, and `AbortSignal`/error mapping in `frontend/src/api/client.ts`, `frontend/src/api/v1/auth.ts`, and `frontend/src/types/auth.ts`
- [x] T032 [US1] Implement **minimal** App shell layout with nav links (Home, Register) only—no NotFound route yet—in `frontend/src/layouts/AppShell.tsx` and baseline styles in `frontend/src/styles/globals.css`
- [x] T033 [US1] Implement Home placeholder page (not the register form) in `frontend/src/pages/Home.tsx`
- [x] T034 [US1] Implement Register page: phone/nickname/role (**no default role—user must choose**), generate `Idempotency-Key`, submit, busy state, success confirmation (user_id, role, not-logged-in copy, masked phone only) in `frontend/src/pages/Register.tsx`
- [x] T035 [US1] Wire React Router routes `/` and `/register` only (defer `*` to US3) in `frontend/src/App.tsx` and entry in `frontend/src/main.tsx`
- [x] T036 [US1] Re-run US1 tests until green; confirm coverage gate for changed domain packages

**Checkpoint**: MVP demo path works end-to-end for happy registration; negative/abuse paths may still be incomplete.

---

## Phase 4: User Story 2 - 安全处理重复与非法注册 (Priority: P1)

**Goal**: Duplicates, concurrency, validation failures, soft-deleted phones, idempotency conflicts/expiry, and rate limits never create extra accounts or leak PII; UI surfaces field/form errors including busy and rate-limit states.

**Independent Test**: Concurrent same-phone registrations → ≤1 user; replay same key → same user_id; occupied phone → `PHONE_ALREADY_REGISTERED`; soft-deleted phone → `ACCOUNT_UNAVAILABLE`; invalid fields → `VALIDATION_ERROR`; rate-limit burst → `RATE_LIMITED`; UI maps each without other-account PII.

### Tests for User Story 2 (write and observe failing first)

- [x] T037 [P] [US2] Add unit tests for field validation errors (phone/nickname/role/idempotency key) mapping to `VALIDATION_ERROR` in `services/api-service/tests/unit/test_registration_validation.py`
- [x] T038 [P] [US2] Add tests for active phone conflict vs soft-deleted `ACCOUNT_UNAVAILABLE` in `services/api-service/tests/integration/test_register_conflicts.py`
- [x] T039 [P] [US2] Add idempotency tests: same key/body replay, same key/different body conflict, expired key after 24h (clock fixture) in `services/api-service/tests/integration/test_register_idempotency.py`
- [x] T040 [P] [US2] Add concurrency test: 100 parallel registers same normalized phone → one user row in `services/api-service/tests/integration/test_register_concurrency.py`
- [x] T041 [P] [US2] Add rate-limit tests for IP 20/15m and phone 5/15m, Redis-unavailable fail-closed 503, and **anti-enumeration** cases (invalid vs valid phone counting rules; `RATE_LIMITED` body/code identical regardless of occupied/soft-deleted/unknown phone) in `services/api-service/tests/integration/test_register_rate_limit.py`
- [x] T042 [P] [US2] Add DB-unavailable / transaction rollback tests ensuring no partial user in `services/api-service/tests/integration/test_register_failures.py`
- [x] T043 [P] [US2] Add frontend tests for field errors, occupied vs unavailable messages, rate-limit banner, busy submit disable, and request_id display in `frontend/src/pages/Register.test.tsx`

### Implementation for User Story 2

- [x] T044 [US2] Extend `RegistrationService` for validation ordering, unique-violation mapping, soft-delete branch, and idempotency conflict/expired paths in `services/api-service/app/domain/users/service.py`
- [x] T045 [US2] Implement Redis fixed-window rate limiter (IP counts every attempt; phone_normalized only after successful normalize), unified `RATE_LIMITED` outcomes, and fail-closed on Redis errors in `services/api-service/app/rate_limit.py`
- [x] T046 [US2] Wire rate limit + error code HTTP mapping (`400/409/429/503/500`) in `services/api-service/app/api/v1/auth.py` per `contracts/business-codes.md`
- [x] T047 [P] [US2] Implement phone masking helper and ensure log redaction for registration paths in `services/api-service/app/domain/users/privacy.py` and `services/api-service/app/observability.py`
- [x] T048 [US2] Map API error codes to Chinese UI messages (field-level + form-level) and preserve inputs on failure in `frontend/src/pages/Register.tsx` and `frontend/src/api/v1/auth.ts`
- [x] T049 [US2] Ensure submit button busy/disabled while in-flight; on timeout/network failure show error (not success); **manual** retry reuses the same idempotency key within session (no auto-retry) in `frontend/src/pages/Register.tsx`
- [x] T050 [US2] Re-run US2 test suite and privacy/concurrency/rate-limit gates until green

**Checkpoint**: US1 still works; US2 safety properties hold at API and UI.

---

## Phase 5: User Story 3 - 初始应用界面骨架可导航 (Priority: P2)

**Goal**: Complete shell **beyond US1 minimal nav**: NotFound/未开放 catch-all, keyboard-accessible form semantics, narrow-viewport layout, developer README. Home/`/register` already exist from US1—extend, do not rebuild.

**Independent Test**: Unknown path shows friendly placeholder with home/register links; keyboard-only can complete primary form interactions; narrow viewport shows submit without horizontal scroll; `/` and `/register` still work (US1 regression).

### Tests for User Story 3 (write and observe failing first)

- [x] T051 [P] [US3] Add route tests for `/`, `/register`, and unknown path rendering NotFound/placeholder in `frontend/src/App.test.tsx`
- [x] T052 [P] [US3] Add accessibility-oriented tests: labeled inputs, error association, keyboard submit path in `frontend/src/pages/Register.test.tsx`
- [x] T053 [P] [US3] Add layout/nav regression test ensuring shell remains on home and register in `frontend/src/layouts/AppShell.test.tsx`

### Implementation for User Story 3

- [x] T054 [P] [US3] Implement NotFound / “暂未开放” page with links to home and register in `frontend/src/pages/NotFound.tsx`
- [x] T055 [US3] Register catch-all route `*` and ensure shell wraps all pages in `frontend/src/App.tsx`
- [x] T056 [P] [US3] Refine semantic form markup (`label htmlFor`, `aria-invalid`, `aria-describedby` for errors) in `frontend/src/pages/Register.tsx`
- [x] T057 [P] [US3] Polish minimal responsive CSS so submit remains visible without horizontal scroll on narrow viewports in `frontend/src/styles/globals.css`
- [x] T058 [US3] Update `frontend/README.md` with local run notes (API base URL, routes) and **manual ER-004 check**: cold dev server, `/register` interactive within 3s on a typical machine (not CI-gated)
- [x] T059 [US3] Re-run frontend test suite until green

**Checkpoint**: Three demonstrable routes + a11y baseline for register form.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Traceability, performance spot-check, docs, and full quickstart.

- [x] T060 [P] Document migration apply/backout and register rollback notes in `services/api-service/README.md`
- [x] T060a [P] Document that `users` and `registration_idempotency_records` inherit API Service PostgreSQL platform backup/restore (no feature-local backup job; soft-delete ≠ restore; idempotency is 24h auxiliary) in `services/api-service/README.md` and cross-link any existing ops PG backup runbook if present under `ops/`
- [x] T061 [P] Add or update ops note for trusted client IP / `X-Forwarded-For` assumptions for rate limit in `ops/runbooks/` (new short runbook or section) without production secrets
- [x] T061a [P] Author registration failure-mode runbook (signals, severity, owner=API Service, triage/recovery for 5xx/503, Redis rate-limit down, conflict/rate-limit floods) in `ops/runbooks/registration.md` (or equivalent under `ops/runbooks/`) with no secrets or full phones
- [x] T061b [P] Add Prometheus alert rule definitions for registration elevated 5xx/`SERVICE_UNAVAILABLE`, rate-limit backend unavailable, and anomalous failure rate under `ops/` (e.g. `ops/alerts/registration.yml` or project-standard alerts path), wired to metrics from `services/api-service/app/observability.py`
- [x] T061c [P] Add or extend a test/fixture that validates alert rule files parse and reference existing metric names in `ops/` or `shared/tests/` (lightweight structural check)
- [x] T062 Run full `make lint` and `make test` from repo root; fix regressions in touched components
- [x] T063 [P] Add p95 latency assertion or documented microbench for register under local integration in `services/api-service/tests/integration/test_register_performance.py` (or mark skip-unless-env with CI guidance)
- [x] T064 Execute manual path from `specs/003-user-registration-ui/quickstart.md` including **§6 first-paint ≤3s** on `/register`, and record any gap fixes in tests/docs
- [x] T065 Verify no Gateway/Billing/Admin registration coupling was introduced (grep/review) and leave those trees unchanged
- [x] T066 Confirm domain package coverage ≥80% and SC-005 redaction scan tests remain green

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Setup — **blocks all user stories**
- **Phase 3 (US1)**: Depends on Foundational — MVP
- **Phase 4 (US2)**: Depends on Foundational; builds on US1 service/router/UI (logically after US1 for less thrash)
- **Phase 5 (US3)**: Depends on Foundational; can partially overlap late US1 (shell already started in T032–T035) but NotFound/a11y complete after US1 routes exist
- **Phase 6 (Polish)**: Depends on US1–US3 desired scope complete

### User Story Dependencies

| Story | Priority | Depends on | Independently testable? |
|-------|----------|------------|-------------------------|
| US1 | P1 | Phase 2 | Yes — happy path API+UI |
| US2 | P1 | Phase 2 (+ US1 code preferred) | Yes — abuse/negative matrix |
| US3 | P2 | Phase 2 (+ US1 shell preferred) | Yes — routing/a11y without backend if mocked |

### Within Each Story

1. Write tests → observe fail  
2. Implement models/services/endpoints or UI  
3. Make tests pass  
4. Checkpoint before next story  

### Parallel Opportunities

- T001–T007 (except T003 lockfile sequencing if contested): parallelize T001/T002/T004–T007 after locks planned  
- T008–T010 foundational tests in parallel  
- T020–T025 US1 tests in parallel  
- T037–T043 US2 tests in parallel  
- T051–T053 US3 tests in parallel  
- Frontend (T031–T035) can proceed against mocked API while API (T026–T030) lands, if contract fixtures are shared  

---

## Parallel Example: User Story 1

```bash
# After Phase 2 complete, launch US1 tests in parallel:
# T020 services/api-service/tests/unit/test_registration_validation.py
# T021 services/api-service/tests/unit/test_registration_service.py
# T022 services/api-service/tests/integration/test_register_api.py
# T023 services/api-service/tests/unit/test_registration_privacy.py
# T024 frontend/src/pages/Register.test.tsx (+ auth.test.ts)
# T025 frontend/src/App.test.tsx

# Then implementation streams:
# API: T026 → T027 → T028 → T029 → T030
# FE:  T031 → T032 → T033 → T034 → T035 (can parallel API after contract stable)
```

---

## Parallel Example: User Story 2

```bash
# Tests in parallel: T037–T043
# Implementation: T044–T046 sequential on service/router; T047 [P]; T048–T049 UI; T050 verify
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 Setup  
2. Complete Phase 2 Foundational  
3. Complete Phase 3 US1  
4. **STOP and VALIDATE** independent test for US1 / quickstart happy path  
5. Demo register e2e without tokens  

### Incremental Delivery

1. Setup + Foundational → foundation ready  
2. US1 → MVP demo  
3. US2 → production-safe registration semantics  
4. US3 → shell/a11y completeness  
5. Polish → CI green + quickstart  

### Suggested staffing split

- Dev A: API Phase 2–4  
- Dev B: Frontend Phase 1/3–5 (after contracts)  
- Sync on OpenAPI field names and business codes  

---

## Notes

- Do **not** implement SF04 login/token, password, SMS, or Gateway registration proxy  
- Soft-deleted re-register must use `ACCOUNT_UNAVAILABLE`, not silent recreate  
- Redis down ⇒ fail-closed register (503), not unlimited writes  
- Commit after each task or logical group; keep Conventional Commits  
- Stop at any checkpoint to validate the story independently  
- Format validation: every task uses `- [ ]`, `Tnnn`, optional `[P]`, story label only in US phases, and exact file paths  

---

## Task Count Summary

| Phase | Tasks | IDs |
|-------|-------|-----|
| Phase 1 Setup | 7 | T001–T007 |
| Phase 2 Foundational | 12 | T008–T019 |
| Phase 3 US1 | 17 | T020–T036 |
| Phase 4 US2 | 14 | T037–T050 |
| Phase 5 US3 | 9 | T051–T059 |
| Phase 6 Polish | 11 | T060–T066 (+ T060a, T061a–c) |
| **Total** | **70** | T001–T066 (+ T060a, T061a–c) |

| User story | Task count (story-labeled) |
|------------|----------------------------|
| US1 | 17 |
| US2 | 14 |
| US3 | 9 |

---

## Phase 7: Convergence

**Purpose**: Close gaps between marked-complete tasks and the present codebase (assessment 2026-07-23). Prior implement pass delivered core handlers/UI but left constitution-required tests, coverage, and several US2/US3 acceptance proofs incomplete.

**Assessment summary**: Domain `service.py` ~39% unit coverage; no automated proofs for concurrency, soft-delete conflict, idempotency expiry, migration backout, HTTP anti-enumeration rate limits, or frontend error-code mapping. Integration happy path is env-gated only.

- [x] T067 Add Alembic upgrade/downgrade tests for `users` and `registration_idempotency_records` in `services/api-service/tests/integration/test_users_migration.py` per FR-005 / Constitution III / plan:migration (missing)
- [x] T068 Add RegistrationService tests covering happy path, validation errors, `PHONE_ALREADY_REGISTERED`, `ACCOUNT_UNAVAILABLE` (soft-deleted fixture), idempotency replay, same-key different body, and 24h expired key in `services/api-service/tests/unit/test_registration_service.py` and/or `services/api-service/tests/integration/test_register_idempotency.py` / `test_register_conflicts.py` per FR-004–007a / SC-001 / SC-003 / US2 (missing)
- [x] T069 Add concurrency test: 100 parallel registers same normalized phone yield at most one `users` row in `services/api-service/tests/integration/test_register_concurrency.py` per FR-008 / SC-002 (missing)
- [x] T070 Add HTTP/integration rate-limit tests for default IP 20/15m and phone 5/15m, Redis-unavailable fail-closed 503, and anti-enumeration (`RATE_LIMITED` shape identical for occupied/soft-deleted/unknown/invalid counting rules) in `services/api-service/tests/integration/test_register_rate_limit.py` per FR-018–020a / SC-009 / ER-002 (missing)
- [x] T071 Add DB-unavailable / transaction rollback tests proving no partial user row in `services/api-service/tests/integration/test_register_failures.py` per ER-005 / Failure scenario 1 (missing)
- [x] T072 Raise and gate line coverage ≥80% for changed domain packages (`app/domain/users/`, registration path) including `service.py` and `auth.py` branches; document or fix CI coverage invocation in `services/api-service/` per Constitution V / T066 (partial)
- [x] T073 Add frontend tests for occupied vs soft-delete unavailable vs rate-limit form errors, busy/disabled submit, and request_id display in `frontend/src/pages/Register.test.tsx` (mock API) per SC-007 / US2 / FR-013–014 / FR-020 (partial)
- [x] T074 Add layout/nav regression tests in `frontend/src/layouts/AppShell.test.tsx` per US3 / T053 (missing)
- [x] T075 Document trusted client IP / `X-Forwarded-For` assumptions for registration rate limiting in `ops/runbooks/registration.md` (or dedicated note under `ops/runbooks/`) per plan:security / T061 (missing)
- [x] T076 Ensure dependency-unavailable registration responses use the unified business envelope (`code`/`message`/`request_id`/`timestamp`) rather than bare FastAPI `detail` in `services/api-service/app/dependencies.py` and `services/api-service/app/api/v1/auth.py` per FR-009 (partial)
- [x] T077 Add env-gated or documented p95 registration latency microbench in `services/api-service/tests/integration/test_register_performance.py` per SC-004 / ER-004 / T063 (missing)
- [x] T078 Add automated log/response redaction scan (or strengthen privacy tests) so full synthetic phones cannot appear in registration log fields or error bodies in `services/api-service/tests/unit/test_registration_privacy.py` (and/or integration) per SC-005 / FR-011 (partial)
