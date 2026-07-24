# Tasks: 本地依赖环境生命周期

**Input**: Design documents from `/specs/002-local-dependency-lifecycle/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Tests are REQUIRED for every behavior change and MUST be written and observed failing before the corresponding implementation task. Documentation-only tasks state their concrete validation target.

**Organization**: Tasks are grouped by user story. US1 and US2 are both P1; all implementation remains behind the SF01 fail-closed activation gate until consumer migration, required documentation, accessibility/security/dirty-worktree gates, and both-platform lifecycle/persistence/recovery/performance evidence pass, after which both public targets, event v2, and help/recovery text activate atomically.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no dependency on another incomplete task in the same batch
- **[Story]**: Maps the task to User Story 1, 2, or 3 from `spec.md`
- Every task names the exact file or files it changes or validates

## Phase 1: Setup (Contract and Supply-Chain Materialization)

**Purpose**: Establish the reviewed architecture decision, versioned public contracts, immutable dependency facts, and locked workflow package before behavior is implemented.

- [X] T001 Accept ADR 002 as the approved pre-implementation design while marking implementation verification Pending, recording ownership, failure modes, both-platform activation gate, volume-preserving rollback, and the no-cleanup boundary in `docs/decisions/002-local-compose-lifecycle.md`
- [X] T002 [P] Materialize lifecycle v1 by copying the reviewed feature contracts into `shared/contracts/local-environment/v1/lifecycle.md` and `shared/contracts/local-environment/v1/local-dependency-manifest.schema.json`
- [X] T003 [P] Materialize Root Make Workflow/event v2 with the required standard envelope and strict workflow-step payload without modifying v1 Make/event artifacts in `shared/contracts/repository-workflow/v2/make-workflow.md` and `shared/contracts/repository-workflow/v2/workflow-event.schema.json`
- [X] T004 [P] Publish health contract v1.1 with the API/Billing-only PostgreSQL 503 readiness shape and unchanged 200/liveness shapes in `shared/contracts/repository-workflow/v1/service-health.openapi.yaml`
- [X] T005 Resolve the official PostgreSQL 15.18, Redis 7.2.14, and Grafana 13.0.3 OCI index plus linux/amd64 and linux/arm64 child digests, verify publisher/runtime UID/GID/license/scan facts, and commit them in `ops/workflow/local-dependencies.json`, `ops/workflow/toolchains.json`, and `docs/decisions/002-local-compose-lifecycle.md`
- [X] T006 [P] Add `workflow.local_env` package discovery and the reviewed asyncpg 0.30.x dependency without changing service locks in `tools/workflow/pyproject.toml` and `tools/workflow/uv.lock`
- [X] T007 Register lifecycle v1, workflow v2, the health 1.1 minor update, ownership, compatibility, and deprecation status in `shared/contracts/README.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the cross-story contract, event, identity, lock, and isolated-test foundations required before any lifecycle story can be implemented.

**CRITICAL**: No user-story implementation begins until this phase passes. T008–T013 are written first and must fail for the intended missing behavior before T014–T018 are implemented.

- [X] T008 [P] Add contract-copy, schema-version, immutable v1 `make-workflow.md`/`workflow-event.schema.json`, health-1.1 minor compatibility, and contract-catalog drift tests in `tests/workflow/test_contracts.py`
- [X] T009 [P] Add workflow event v2 tests for unique event IDs, stable type/version/producer, UTC timestamps, lifecycle correlation, strict payloads, dependency-field, WAITING-state, diagnostic-code, ordering, redaction, and strict-consumer migration in `tests/workflow/test_local_env_events.py`
- [X] T010 [P] Add manifest tests rejecting placeholder/tag-only/leaf-only digests, missing platform children, extra dependencies, unsafe runtimes, invalid UID/GID, and timeout drift in `tests/workflow/test_local_dependency_manifest.py`
- [X] T011 [P] Add typed state-machine and serialization-exclusion tests for manifest, operation, dependency, health, secret, and readiness entities in `tests/workflow/test_local_env_models.py`
- [X] T012 [P] Add canonical path, NFC/UTF-8 hash, spaces/non-ASCII/symlink, short-hash collision, secure runtime directory, lock-file safety, contention, and abnormal-holder-exit tests in `tests/workflow/test_local_env_identity.py`
- [X] T013 [P] Replace the transition-only assertions with an explicit v2 consumer-migration and activation gate that keeps public dev/dev-down on `SF02_NOT_READY` until all required capabilities are present in `tests/workflow/test_sf02_transition.py`
- [X] T014 [P] Implement immutable typed entities, manifest loading, exact three-dependency validation, safe repr/equality behavior, and lifecycle state transitions in `tools/workflow/local_env/__init__.py` and `tools/workflow/local_env/models.py`
- [X] T015 [P] Implement workflow event v2 standard-envelope emission with UUID event IDs, stable type/version/producer, UTC timestamps, lifecycle correlation IDs, strict dependency payloads, WAITING semantics, stable SF02 diagnostics, bounded messages, and value redaction while preserving v1 history in `tools/workflow/events.py`
- [X] T016 Migrate every repository-owned JSONL reader and fixture assertion to the event v2 standard envelope while retaining explicit v1 Make/event regression coverage in `tests/workflow/helpers.py`, `tests/workflow/test_events.py`, and `tests/workflow/test_command_contract.py`
- [X] T017 Implement canonical physical-path identity, full-fingerprint ownership, secure per-user runtime/project directories, no-symlink 0600 lock files, and non-blocking `fcntl` locking in `tools/workflow/local_env/identity.py`
- [X] T018 Create synthetic-secret, temporary-workspace, monotonic-clock, fake-subprocess, and test-only project-label factories that can never address a developer project in `tests/workflow/conftest.py`

**Checkpoint**: Versioned contracts validate, v1 regression coverage remains green, event v2 consumers are migrated, unsafe manifests fail closed, and identity/lock behavior passes without Docker.

---

## Phase 3: User Story 1 - 一次启动并确认依赖真正可用 (Priority: P1) MVP Development Slice

**Goal**: Reconcile exactly PostgreSQL, Redis, and Grafana from validated local configuration and return fresh authenticated per-dependency readiness under one bounded deadline.

**Independent Test**: Against an isolated test project on a supported local runtime, invoke the guarded lifecycle start adapter with valid ignored configuration; verify missing immutable images are pulled and reported separately, all three authenticated probes pass within 60 seconds, a healthy repeat finishes within 15 seconds without resource growth or registry access, and every failure retains inspectable state. Public activation remains gated through US2, US3, and the final cross-platform release evidence.

### Tests for User Story 1 (write and observe failing first)

- [X] T019 [P] [US1] Add strict `.env.local` parsing, mode-origin, URL grammar, loopback, placeholder, percent-decoding, synthetic-secret, duplicate-port, derived-connection, and field-name-only error tests in `tests/workflow/test_local_env_config.py`
- [X] T020 [P] [US1] Add Compose structural tests for exactly three index-digest images, canonical services, loopback long-syntax ports, isolated network, PostgreSQL/Redis named volumes, Grafana 0700 tmpfs, non-root users, 0400 environment-source secrets, authenticated healthchecks, grace periods, and forbidden forms in `infra/tests/test_local_compose.py`
- [X] T021 [P] [US1] Add fake CLI tests for fixed Compose argument order, verified YAML bytes over stdin, safe project directory, local endpoint/platform/capability checks, pull-missing/up-never sequencing, JSON parsing, ownership checks, port races, interruption, and redacted errors in `tests/workflow/test_local_env_compose.py`
- [X] T022 [P] [US1] Add lifecycle tests for read-only preflight ordering, in-lock revalidation, separate pull timing, one non-extendable 60-second deadline, concurrent probes, healthy fast path, partial failure retention, timeout edges, retry convergence, and aggregate failure semantics in `tests/workflow/test_local_env_lifecycle.py`
- [X] T023 [P] [US1] Add bounded probe tests for PostgreSQL authenticated `SELECT 1`, Redis AUTH/PING on one connection, Grafana health/admin identity, remaining-time truncation, stale-result rejection, recovery, and safe diagnostic mapping in `tests/workflow/test_local_env_probes.py`
- [X] T024 [P] [US1] Add security and terminal accessibility tests proving mode/config rejection precedes coordination or Docker access, secrets/paths/raw output never enter unsafe surfaces, and new plain-text/JSONL output remains `NO_COLOR`, screen-reader, non-interactive, no-icon and exit-status understandable in `tests/workflow/test_local_env_security.py` and `tests/workflow/test_accessibility_performance.py`
- [X] T025 [P] [US1] Add isolated real-Compose and deterministic performance-harness tests for cold start, separate missing-image timing, predeclared 20-trial batches, ten healthy repeats, dynamic loopback ports, authenticated host/project-network probes, wrong auth, port conflict/race, stopped/stale/partial states, daemon loss, timeout, and retained failure state in `tests/workflow/test_local_env_integration.py` and `tests/workflow/test_local_env_performance.py`

### Implementation for User Story 1

- [X] T026 [P] [US1] Implement pure mode-first `.env.local` parsing, strict local URL/secret validation, pairwise port checks, safe displayed endpoints, and derived container connections in `tools/workflow/local_env/config.py`
- [X] T027 [P] [US1] Define exactly PostgreSQL, Redis, and Grafana with reviewed digest references, canonical DNS, loopback publishers, project network, declared storage, non-root secret files, authenticated healthchecks, and 60/30/30 grace periods in `infra/docker/compose.local.yml`
- [X] T028 [US1] Implement the local-runtime and Compose adapter with committed-blob verification, stdin transport, fixed safe arguments, captured JSON state, publisher/owner inspection, missing-only pull, current-platform digest verification, and bounded subprocess termination in `tools/workflow/local_env/compose.py`
- [X] T029 [P] [US1] Implement bounded PostgreSQL, Redis, and Grafana authenticated probes with fresh evidence, safe categories, and deadline-aware retry in `tools/workflow/local_env/probes.py`
- [X] T030 [US1] Implement dedicated child-only Compose secret mappings, PostgreSQL/Grafana password files, injection-safe single-directive Redis config, verified file ownership/mode, and parse-only teardown placeholders in `tools/workflow/local_env/compose.py`
- [X] T031 [US1] Implement start orchestration from read-only preflight through lock/revalidation, image pull/verify, reconcile, concurrent fresh probes, standard-envelope/plain-text aggregation, resource-retaining failure, and idempotent retry in `tools/workflow/local_env/lifecycle.py`
- [X] T032 [US1] Add an internal guarded dev dispatch path that exercises the new lifecycle in tests but preserves public v1 `SF02_NOT_READY` behavior until the activation gate passes in `tools/workflow/cli.py`
- [X] T033 [P] [US1] Declare MODE, DATABASE_URL, REDIS_URL, GRAFANA_URL, and GRAFANA_ADMIN_PASSWORD with classifications, local-only intent, URL-derived port rules, and unusable placeholders in `.env.example`
- [X] T034 [P] [US1] Document the exact three-service Compose model, immutable image policy, loopback/network addresses, persistence classes, secret transport, and no-business-service boundary in `infra/docker/README.md`
- [X] T035 [US1] Implement disposable real-Compose fixtures and the shared cross-platform performance harness with dynamic ports, synthetic credentials/data, exact test labels, predeclared trial accounting, project-network probe input over stdin, and fixture-only teardown guards in `tests/workflow/conftest.py`

**Checkpoint**: The startup adapter passes US1 unit, contract, security, fake-subprocess, and real-dependency tests while the public activation gate still fails closed.

---

## Phase 4: User Story 2 - 非破坏性停止并安全恢复 (Priority: P1) Guarded Release-Candidate Slice

**Goal**: Stop only the exact workspace project without configuration secrets, preserve named volumes and PostgreSQL facts, recover from partial/interrupted state, serialize conflicts, and complete a guarded two-target candidate without activating the public lifecycle before the final release gate.

**Independent Test**: Start an isolated environment, write a PostgreSQL marker, run dev-down twice with `.env.local` unavailable, restart, and repeat for ten cycles; verify the marker is retained, Redis may be empty, no duplicate/orphan resources appear, Grafana has no anonymous volume, no unrelated project changes, and 100 conflicting operations produce safe retryable outcomes.

### Tests for User Story 2 (write and observe failing first)

- [X] T036 [P] [US2] Extend ownership and workspace-preservation tests for same-path stability, branch independence, different clone/worktree isolation, move detection, report-only old resources, full-fingerprint collision failure, path-free labels, and unchanged dirty tracked/untracked/symlink files across dev/dev-down in `tests/workflow/test_local_env_identity.py` and `tests/workflow/test_local_env_dirty_worktree.py`
- [X] T037 [P] [US2] Add fake Compose down tests for missing config, parse-only secrets, exact project/fingerprint authorization, already-stopped volume-only state, stopped containers, orphan networks, `down --remove-orphans`, 75-second bound, forbidden volume/image/prune flags, and exact-label fallback in `tests/workflow/test_local_env_compose_down.py`
- [X] T038 [P] [US2] Add lifecycle down tests for identity-before-config, immediate lock, graceful stop verification, repeated success, named-volume retention, partial failure, retry, moved-workspace reporting, and safe final events in `tests/workflow/test_local_env_down.py`
- [X] T039 [P] [US2] Add 100-run repeated-start/start-vs-down contention, lock-holder interruption, port-race, no-duplicate-resource, no-volume-delete, and retryable-loser tests in `tests/workflow/test_local_env_concurrency.py`
- [X] T040 [P] [US2] Add ten start/down/restart cycle tests with PostgreSQL marker retention, empty-Redis tolerance, stable volume identities, no orphan network, no Grafana anonymous volume, and no schema/migration/seed action in `tests/workflow/test_local_env_persistence.py`
- [X] T041 [P] [US2] Add recovery tests for stopped/unhealthy containers, daemon loss, SIGINT, failed down, stale health, wrong persisted PostgreSQL credentials, and direct convergence without implicit cleanup or role mutation in `tests/workflow/test_local_env_recovery.py`

### Implementation for User Story 2

- [X] T042 [P] [US2] Extend identity discovery and mutation authorization with exact project/full-fingerprint checks, collision failure, path-free labels, and mandatory report-only moved-workspace findings in `tools/workflow/local_env/identity.py`
- [X] T043 [US2] Implement config-free exact-project down, parse-only secret parsing, bounded graceful stop, state/volume verification, and exact-label container/network fallback without volume, image, or prefix-wide removal in `tools/workflow/local_env/compose.py`
- [X] T044 [US2] Implement dev-down orchestration, already-stopped idempotency, named-volume preservation, moved-workspace guidance, safe failure retention, and final per-dependency events in `tools/workflow/local_env/lifecycle.py`
- [X] T045 [US2] Implement reconciliation for interrupted start/stop, stopped/stale/partial exact-owned resources, desired-image replacement with volume retention, daemon recovery, and credential-drift failure without implicit mutation in `tools/workflow/local_env/lifecycle.py`
- [X] T046 [US2] Enforce one lock across every mutable phase and final event so losing repeated/conflicting operations return `OPERATION_IN_PROGRESS` without pull, probe, resource, or volume side effects in `tools/workflow/local_env/lifecycle.py`
- [X] T047 [US2] Preserve root target names and mode forwarding while preparing activation-ready help, side-effect, retention, and recovery text that remains pending until the final atomic switch in `Makefile`
- [X] T048 [US2] Add guarded fault-injection, process-interruption, resource-count, marker-retention, Redis-reset, and exact-test-project cleanup helpers that cannot select a developer project in `tests/workflow/conftest.py`
- [X] T049 [US2] After T042–T048 pass, complete the activation-candidate event-v2 and real dev/dev-down dispatch behind the existing fail-closed guard without removing public runtime `SF02_NOT_READY` in `tools/workflow/cli.py`

**Checkpoint**: Both P1 activation-candidate stories pass through guarded adapters; startup and stop are idempotent, serialized, non-destructive, isolated, and safely recoverable, while public root targets still fail closed with `SF02_NOT_READY`.

---

## Phase 5: User Story 3 - 使用稳定地址连接并诊断不可用状态 (Priority: P2)

**Goal**: Provide one host/container connection contract and dependency-aware readiness for API Service and Billing Service only, without changing liveness, Gateway/Admin behavior, or starting business services.

**Independent Test**: Verify host and canonical project-network authenticated connections for all three dependencies, then independently run API and Billing with injectable probes; PostgreSQL outage must leave liveness at 200, make readiness return the exact safe 503 response within two seconds, and recover to the unchanged 200 shape without service restart.

### Tests for User Story 3 (write and observe failing first)

- [X] T050 [P] [US3] Add tests that host URLs remain the sole facts, container URLs replace only host/port with postgres/redis/grafana, safe output strips user-info, and no competing port/container URL fields exist in `tests/workflow/test_local_env_connections.py`
- [X] T051 [P] [US3] Add project-network integration tests that execute a real PostgreSQL query, Redis AUTH/PING, and Grafana health/admin HTTP request rather than DNS-only checks in `tests/workflow/test_local_env_connectivity.py`
- [X] T052 [P] [US3] Add API Service contract and observability tests for unchanged liveness/ready-200 shapes, exact safe 503 dependency shape, request IDs, invalid-config/auth/query/timeout mapping, recovery without restart, probe total/failure counters, duration histogram, and secret-free bounded labels in `services/api-service/tests/test_health.py` and `services/api-service/tests/test_readiness_metrics.py`
- [X] T053 [P] [US3] Add API Service database tests for safe URL driver mapping, lifespan-owned engine, `pool_pre_ping`, bounded async `SELECT 1`, no retries, shutdown disposal, and real PostgreSQL recovery in `services/api-service/tests/test_database_readiness.py`
- [X] T054 [P] [US3] Add Billing Service contract and observability tests for unchanged liveness/ready-200 shapes, exact safe 503 dependency shape, request IDs, invalid-config/auth/query/timeout mapping, recovery without restart, probe total/failure counters, duration histogram, and secret-free bounded labels in `services/billing-service/tests/test_health.py` and `services/billing-service/tests/test_readiness_metrics.py`
- [X] T055 [P] [US3] Add Billing Service database tests for safe URL driver mapping, lifespan-owned engine, `pool_pre_ping`, bounded async `SELECT 1`, no retries, shutdown disposal, and real PostgreSQL recovery in `services/billing-service/tests/test_database_readiness.py`
- [X] T056 [P] [US3] Add boundary assertions that Gateway/Admin gain no dependency probes, no business service is started by dev, and no business route/schema/migration/seed behavior is introduced in `tests/workflow/test_boundaries.py`

### Implementation for User Story 3

- [X] T057 [US3] Emit matching redacted host endpoints and canonical container addresses from the validated connection projections without serializing credentials in `tools/workflow/local_env/config.py` and `tools/workflow/local_env/lifecycle.py`
- [X] T058 [P] [US3] Implement API Service's owned two-second async PostgreSQL `SELECT 1` probe, SQLAlchemy engine factory, safe error categories, and shutdown disposal in `services/api-service/app/database.py`
- [X] T059 [US3] Wire the API probe through lifespan/application state, keep `/health/live` independent, preserve the ready-200 shape, return only the contracted PostgreSQL 503 result, and record safe probe total/failure/duration metrics in `services/api-service/app/main.py`, `services/api-service/app/health.py`, and `services/api-service/app/observability.py`
- [X] T060 [P] [US3] Implement Billing Service's owned two-second async PostgreSQL `SELECT 1` probe, SQLAlchemy engine factory, safe error categories, and shutdown disposal in `services/billing-service/app/database.py`
- [X] T061 [US3] Wire the Billing probe through lifespan/application state, keep `/health/live` independent, preserve the ready-200 shape, return only the contracted PostgreSQL 503 result, and record safe probe total/failure/duration metrics in `services/billing-service/app/main.py`, `services/billing-service/app/health.py`, and `services/billing-service/app/observability.py`
- [X] T062 [P] [US3] Implement isolated fake-probe and real-PostgreSQL fixtures for API readiness without exposing URLs or exception bodies in `services/api-service/tests/conftest.py`
- [X] T063 [P] [US3] Implement isolated fake-probe and real-PostgreSQL fixtures for Billing readiness without exposing URLs or exception bodies in `services/billing-service/tests/conftest.py`
- [X] T064 [P] [US3] Document independent service startup, PostgreSQL liveness/readiness semantics, two-second bound, recovery, and the no-lifecycle-management boundary in `services/api-service/README.md` and `services/billing-service/README.md`

**Checkpoint**: Container/host connection contracts pass; API and Billing recover readiness independently; liveness, Gateway, Admin, and the dev dependency set remain unchanged.

---

## Phase 6: Polish & Cross-Cutting Release Evidence

**Purpose**: Complete safe operating guidance, global quality gates, cross-platform performance evidence, usability validation, and rollout/rollback traceability.

- [X] T065 [P] Write the repository-workflow-owner diagnostic, safe inspection, port/auth/runtime/timeout/credential-drift recovery, moved-workspace, interruption, persistence, accessibility, evidence ownership, and non-destructive stop procedures in `ops/runbooks/local-environment.md`
- [X] T066 [P] Update developer navigation, prerequisites, root workflow effects, supported platforms, service names, safe addresses, and SF02/SF19 scope boundaries in `README.md`, `ops/README.md`, and `AGENTS.md`
- [X] T067 Add final negative assertions for secret/path leakage, remote/wildcard endpoints, unsafe dependency identities, runtime lockfile mutation, package-discovery drift, dirty tracked/untracked worktree changes, inaccessible terminal output, forbidden cleanup/migration, and unrelated-resource mutation in `tests/workflow/test_secret_scan.py`, `tests/workflow/test_dependency_scans.py`, `tests/workflow/test_local_env_dirty_worktree.py`, `tests/workflow/test_accessibility_performance.py`, and `tests/workflow/test_boundaries.py`
- [X] T068 Run format, lint, type-check, contract drift, unit/contract/integration/recovery, accessibility, dirty-worktree, readiness-metric, secret/dependency/container scans, coverage, build, and migration-no-change gates through `Makefile`, and record redacted command results in `specs/002-local-dependency-lifecycle/evidence/quality-gates.md`
- [X] T069 Execute the committed shared performance harness on Linux x86_64 for 20 cold trials with at least 19 within 60 seconds, ten repeats within 15 seconds, ten persistence cycles, native image identity, signal/recovery, and standard event-v2 envelope checks, recording environment and aggregate evidence in `specs/002-local-dependency-lifecycle/evidence/linux-amd64.md`
- [ ] T070 Execute the same committed performance harness on macOS arm64 for native image identity, NFC/path behavior, Docker Desktop loopback, secret ownership, stop signals, 20 cold trials, ten repeats, persistence, and standard-envelope parity, recording environment and aggregate evidence in `specs/002-local-dependency-lifecycle/evidence/macos-arm64.md`
- [ ] T071 Have the repository workflow owner run the committed ten-person documentation-only protocol with qualified first-time SF02 participants, requiring at least nine to complete setup, start, status confirmation, and recovery discovery within ten minutes, and record only aggregate redacted evidence in `specs/002-local-dependency-lifecycle/evidence/developer-usability.md`
- [X] T072 Execute every safe scenario in `specs/002-local-dependency-lifecycle/quickstart.md` and create a redacted evidence index linking quality, platform, persistence, readiness, security, and usability results in `specs/002-local-dependency-lifecycle/evidence/README.md`
- [X] T073 Finalize requirement-to-test traceability, dependency/security/schema impact, activation/deprecation notice, immutable artifact identity, volume-preserving rollback decision point, and evidence links while leaving ADR implementation verification Pending in `docs/decisions/002-local-compose-lifecycle.md` and `specs/002-local-dependency-lifecycle/quickstart.md`
- [ ] T074 Only after T065–T073 and both-platform evidence pass, atomically remove runtime `SF02_NOT_READY`, make real dev/dev-down plus event v2 the default, publish matching help/recovery text, and mark ADR implementation verification Verified in `tools/workflow/cli.py`, `Makefile`, and `docs/decisions/002-local-compose-lifecycle.md`

---

## Requirements Traceability

| Requirement | Implementation and evidence tasks |
|-------------|-----------------------------------|
| FR-001 | T001, T003, T013, T032, T047–T049, T065–T074 |
| FR-002 | T010, T020, T027, T031, T056, T067 |
| FR-003 | T005, T010, T021, T025, T027–T028, T069–T070 |
| FR-004 | T019, T021–T024, T026, T028, T031 |
| FR-005 | T019, T024, T026, T033, T050, T067 |
| FR-006 | T024, T033, T067 |
| FR-007 | T019–T020, T026–T027, T034, T050, T057, T064–T066 |
| FR-008 | T019, T026, T050, T057 |
| FR-009 | T020, T025, T027, T034, T051, T067, T069–T070 |
| FR-010 | T021–T022, T025, T028, T031, T039, T041 |
| FR-011 | T020, T023, T025, T027, T029, T051 |
| FR-012 | T020, T023, T025, T027, T029, T051 |
| FR-013 | T009, T022, T025, T029, T031, T069–T070 |
| FR-014 | T022, T025, T031, T039, T069–T070 |
| FR-015 | T022, T025, T031, T041, T045, T065 |
| FR-016 | T012, T017, T021, T024, T028, T036, T042, T067, T069–T070 |
| FR-017 | T037–T040, T043–T044, T047–T048 |
| FR-018 | T037–T038, T043–T044 |
| FR-019 | T036, T038, T041–T042, T044, T065 |
| FR-020 | T020, T037, T040–T045, T048, T067, T069–T070 |
| FR-021 | T020, T040, T044, T048, T069–T070 |
| FR-022 | T020, T024, T037, T040, T043, T067 |
| FR-023 | T012, T017, T039, T041, T046, T048 |
| FR-024 | T034, T047, T064–T066, T071–T072 |
| FR-025 | T004, T008, T052–T064 |
| FR-026 | T003, T007, T009, T013, T015–T016, T022, T031, T038, T044, T047, T049, T069–T070, T074 |
| FR-027 | T006, T021, T024, T028, T040, T056, T067–T068 |
| FR-028 | T012, T017, T024, T028, T036, T042, T066–T070 |
| FR-029 | T005, T010, T021, T028, T066, T069–T070, T074 |
| ER-001 | T001–T009, T013–T016, T049, T073–T074 |
| ER-002 | T018–T020, T024, T026–T030, T033, T037, T052–T063, T067–T070 |
| ER-003 | T036–T049, T067, T069–T070 |
| ER-004 | T022, T025, T035, T039–T040, T053, T055, T069–T070 |
| ER-005 | T011–T012, T017, T022–T023, T031, T037–T046 |
| ER-006 | T009, T015, T022, T031, T038, T044, T052, T054, T059, T061, T065, T068–T070 |
| ER-007 | T024, T047, T065–T071 |
| SC-001 | T025, T035, T069–T070 |
| SC-002 | T022, T025, T039, T069–T070 |
| SC-003 | T040, T048, T069–T070 |
| SC-004 | T019, T021–T025, T037–T041, T052–T055, T067 |
| SC-005 | T019, T025, T034, T050–T051, T057, T064–T066, T069–T070 |
| SC-006 | T038–T049, T069–T070 |
| SC-007 | T009, T015, T024, T052–T063, T067–T070 |
| SC-008 | T047, T065–T066, T071–T072 |
| SC-009 | T012, T017, T039, T041, T046, T048, T069–T070 |

Every story checkpoint uses this matrix to verify that implementation and required evidence remain linked; T073 converts the completed rows into PR/release evidence rather than creating traceability for the first time.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Starts immediately. T002, T003, T004, and T006 can proceed in parallel; T005 requires ADR ownership context from T001; T007 follows the contract copies.
- **Phase 2 (Foundational)**: Depends on Phase 1. T008–T013 are the failing-test batch; T014–T018 implement the shared contract/event/model/identity/test foundations and block all story code.
- **Phase 3 (US1)**: Depends on Phase 2. T019–T025 must fail before T026–T035. US1 is independently testable through the guarded lifecycle adapter but does not change the public v1 behavior yet.
- **Phase 4 (US2)**: Depends on the shared US1 adapter in T026–T035. T036–T041 must fail before T042–T049. T049 completes only a guarded activation candidate; public activation remains prohibited until T074.
- **Phase 5 (US3)**: Fake-probe service work can start after Phase 2; T051 and the real PostgreSQL portions of T053/T055 depend on the P1 environment. Complete US3 after the two P1 stories to preserve priority order.
- **Phase 6 (Polish)**: Depends on all selected stories. Platform, usability, and release evidence require the full implementation and all automated gates.

### User Story Dependency Graph

```text
Setup -> Foundational -> US1 startup core -> US2 guarded lifecycle candidate -> US3 connectivity/readiness -> Release evidence + atomic activation
                                  \-------------------------------------------> US3 fake-probe work
```

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational for implementation and isolated testing. It deliberately remains behind the activation gate.
- **US2 (P1)**: Reuses US1's Compose/lifecycle core and proves the safety conditions required by the plan while leaving US1+US2 behind the fail-closed public gate.
- **US3 (P2)**: Service fake-probe behavior is independent after Foundational; full connectivity evidence depends on the P1 local environment. API and Billing implementations remain independent of each other.

### Within Each User Story

- Write the story's test tasks first and confirm they fail for the intended missing behavior.
- Implement pure validation and models before side-effecting adapters.
- Implement adapters/probes before orchestration and public dispatch.
- Keep one non-extendable deadline and one exact ownership/lock boundary across integration.
- Finish negative, recovery, security, and real-dependency evidence before declaring the story complete.

## Parallel Execution Examples

### User Story 1

```text
Parallel failing-test batch: T019 config | T020 Compose structure | T021 fake CLI | T023 probes | T024 security
Parallel implementation batch after those tests: T026 config | T027 Compose asset | T029 probes | T033 example config | T034 infra docs
Then serialize integration: T028 -> T030 -> T031 -> T032 -> T035
```

### User Story 2

```text
Parallel failing-test batch: T036 identity/move | T037 Compose down | T038 lifecycle down | T039 concurrency | T040 persistence | T041 recovery
Implementation order: T042 -> T043 -> T044 -> T045 -> T046 -> T047 -> T048 -> T049
```

### User Story 3

```text
Parallel failing-test batch: T050 connection facts | T051 network probes | T052-T053 API | T054-T055 Billing | T056 boundaries
Parallel service implementation: T058 API database | T060 Billing database
Parallel integration fixtures after service wiring: T062 API fixtures | T063 Billing fixtures | T064 service docs
```

## Implementation Strategy

### MVP Development Slice

1. Complete Setup and Foundational.
2. Complete US1 through T035 and validate the startup adapter independently.
3. Keep public dev/dev-down fail-closed; do not ship a start-only lifecycle.

### P1 Release Candidate

1. Complete both P1 stories through T049.
2. Verify persistence, isolation, redaction, recovery, concurrency, and v2 consumer migration.
3. Keep dev/dev-down and event v2 behind the runtime `SF02_NOT_READY` guard.
4. Continue through P2 and the shared cross-platform release gates; a P1-only candidate is not publicly activated.

### First Public Release

1. Complete US3, T065–T073, and all automated, usability, security, dirty-worktree, persistence, recovery, and performance gates.
2. Obtain passing Linux amd64 and macOS arm64 evidence from the same committed harness.
3. Activate dev/dev-down, event v2, help text, and ADR implementation verification atomically at T074.

### Incremental Delivery

1. Contract/supply-chain foundation with immutable v1 history and v2 migration gate.
2. US1 startup core behind the gate.
3. US2 safe stop as a guarded P1 candidate.
4. US3 stable connectivity plus independent API/Billing readiness.
5. Cross-platform, usability, security, and release evidence followed by the single atomic public activation.

## Notes

- `[P]` marks file-disjoint work only; tasks that converge on `compose.py`, `lifecycle.py`, `cli.py`, or shared test fixtures are intentionally serialized.
- Test-only teardown is authorized solely for exact test-labeled projects; no task adds a developer-facing destructive cleanup target.
- No task adds Kafka/Redpanda, Prometheus, Loki, MinIO, frontend, Gateway, Admin, or business-service startup to `make dev`.
- No task creates a business schema, Alembic revision, seed, production/test resource access, host secret file, service-environment secret, anonymous volume, wildcard bind, or remote-daemon path.
- Commit after each task or coherent test-first pair, preserving Conventional Commit scope and the v2 activation gate.

---

## Phase 7: Convergence

**Purpose**: Close implementation gaps found after `/speckit-implement` where tasks were marked complete but code or automated evidence still only partially satisfies the spec/plan. Phase 6 release tasks T067–T074 remain open and are not restated here.

- [X] T075 [P] Expand concurrency coverage beyond serial downs: 100-run repeated start/start and start-vs-down contention, mid-hold lock-holder interruption, port-race loser behavior, no duplicate resources, no volume delete, and retryable `OPERATION_IN_PROGRESS` losers with zero side effects in `tests/workflow/test_local_env_concurrency.py` and, where required, fake adapter seams in `tests/workflow/conftest.py` per FR-023, SC-006, US2 Independent Test (partial)
- [X] T076 Add real-Compose ten-cycle start/down/restart persistence proving a written PostgreSQL marker row is retained, Redis emptiness is tolerated, volume identities stay stable, no orphan network or Grafana anonymous volume appears, and no schema/migration/seed runs in `tests/workflow/test_local_env_persistence.py` using `RealComposeProjectFactory` per US2/AC3, FR-020, FR-021, SC-003 (partial)
- [X] T077 Map `KeyboardInterrupt`/SIGINT during `start_local_environment` and `stop_local_environment` to `OperationStatus.INTERRUPTED` with retained project resources, safe redacted final events, and lock release in `tools/workflow/local_env/lifecycle.py` per spec Edge Cases (interrupt signal) and FR-015 (missing)
- [X] T078 [P] Replace the `SF02_REAL_COMPOSE` placeholder in `tests/workflow/test_local_env_connectivity.py` with authenticated project-network probes via `NetworkProbeRunner` for PostgreSQL `SELECT 1`, Redis AUTH/PING, and Grafana health/admin HTTP (not DNS-only) per US3/AC1, FR-011, FR-012, plan Phase D (partial)
- [X] T079 Complete guarded T048 helpers so fault-injection can interrupt a held lifecycle, resource counts reflect exact `tmtest-` labels only, and PostgreSQL marker/Redis-reset helpers are usable by persistence/recovery suites without addressing developer projects in `tests/workflow/conftest.py` per plan Phase D / T048 (partial)
- [X] T080 Add recovery tests that exercise the T077 interrupt path, daemon-loss fail-closed diagnostics without mutation, and post-interrupt direct convergence without implicit cleanup or role mutation in `tests/workflow/test_local_env_recovery.py` per T041, FR-015, plan Phase D (partial)

---

## Phase 8: Convergence

**Purpose**: Residual gaps after Phase 7 implement. Phase 6 release/activation tasks T068–T074 remain open and are not restated.

- [X] T081 [P] Complete residual T067 negatives: SF02 lifecycle event/plain-text secret and workspace-path leakage assertions in `tests/workflow/test_secret_scan.py` (or lifecycle redaction suite), and replace the `assert True` scanner fail-closed stub with a real non-zero-exit contract in `tests/workflow/test_dependency_scans.py` per FR-006, Constitution II, T067 (partial)
- [X] T082 Finish T077 residuals: use the returned `OperationStatus.INTERRUPTED` transition (do not discard the immutable result) for any diagnostic/accounting that needs it, and add a `start_local_environment` KeyboardInterrupt test proving retained resources, lock release, and safe final events in `tools/workflow/local_env/lifecycle.py` and `tests/workflow/test_local_env_recovery.py` (or lifecycle tests) per Edge Cases (interrupt), FR-015 (partial)
