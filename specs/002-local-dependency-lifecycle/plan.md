# Implementation Plan: 本地依赖环境生命周期

**Branch**: `002-local-dependency-lifecycle` | **Date**: 2026-07-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-local-dependency-lifecycle/spec.md`

## Summary

Replace SF01's fail-closed `SF02_NOT_READY` transition with a real, bounded and non-destructive local lifecycle behind the unchanged `make dev` and `make dev-down` targets. Because success and side-effect semantics change, publish Root Make Workflow/event v2 and migrate every repository consumer before activation. The maintained Python workflow tool will validate an ignored local configuration, derive a collision-checked path-hash Compose project identity, serialize operations with a secure POSIX advisory lock, pull only reviewed multi-platform image digests, reconcile PostgreSQL 15/Redis 7/Grafana on a loopback-only project network, perform authenticated readiness under one 60-second deadline, and preserve PostgreSQL/Redis named volumes on ordinary down.

The implementation is contract-first and test-first. It introduces a versioned local-dependency manifest, creates workflow event v2 as a constitution-compliant standard envelope whose payload carries dependency/waiting/stable SF02 diagnostics, and adds a backward-compatible health-contract minor update: API Service and Billing Service retain independent liveness but return 503 readiness when their bounded PostgreSQL `SELECT 1` probe fails and expose safe Prometheus probe totals, failures, and durations. No business service is started, no migration/schema/seed is run, no destructive cleanup action is added, and Gateway/Admin readiness remains unchanged.

## Technical Context

**Language/Version**: Python 3.11.15 for root workflow/lifecycle and FastAPI readiness; GNU Make 3.81-compatible entry adapters; Docker Compose YAML; JSON/JSON Schema 2020-12; OpenAPI 3.1; Markdown runbooks

**Primary Dependencies**: Existing independently uv-locked `tools/workflow` package using Python standard library (`urllib.parse`, `hashlib`, `unicodedata`, `socket`, `fcntl`, `subprocess`) plus a reviewed asyncpg 0.30.x addition for the PostgreSQL host query; Docker Engine/CLI 29.5.3 and Docker Compose 5.1.4; PostgreSQL `15.18-bookworm`, Redis `7.2.14-bookworm`, Grafana OSS `13.0.3`, each fixed by reviewed index and child digests; existing FastAPI 0.115.x, SQLAlchemy asyncio 2.0.x and asyncpg 0.30.x locks in API/Billing

**Storage**: PostgreSQL project-scoped named volume is the durable local fact source; Redis project-scoped named volume is preserved but semantically rebuildable; Grafana `/var/lib/grafana` is explicit tmpfs with no anonymous/named volume; secrets move from a dedicated Compose child environment into UID/GID-owned 0400 container secret files and never become host files; no new business table, local metadata database, or production data

**Testing**: pytest/pytest-asyncio unit and subprocess contract tests under `tests/workflow/`; JSON Schema/OpenAPI/Compose structural tests; fake Compose adapter tests; real isolated Docker Compose integration with synthetic credentials/dynamic loopback ports; API/Billing FastAPI probe-injection and real PostgreSQL query tests; ten-cycle persistence/idempotency/concurrency/recovery suites; Linux x86_64 CI plus separate representative macOS arm64 performance evidence

**Target Platform**: macOS arm64 with local Docker Desktop Linux containers and Linux x86_64 with local Docker Engine; native `linux/arm64`/`linux/amd64` image variants from the same OCI index; remote contexts/endpoints and all other host/architecture combinations are unsupported

**Project Type**: Polyglot monorepo feature spanning a developer lifecycle CLI, declarative local infrastructure, versioned shared developer/health contracts, two independently owned Python service readiness adapters, tests and runbook documentation

**Performance Goals**: Image acquisition measured separately; after all images are available, at least 95% of normal cold readiness runs complete within 60 seconds on each supported host class; ten healthy repeat starts each complete within 15 seconds without registry access or resource-count growth; API/Billing readiness completes within a two-second total probe timeout; conflict/preflight failures occur before resource mutation

**Constraints**: Root Makefile only public workflow; dependency set exactly PostgreSQL/Redis/Grafana; no system tool install/upgrade, `sudo`, remote daemon, business-service start, Kafka/Prometheus/Loki/MinIO, migration, seed, production/test access, tag-only/latest image, wildcard/LAN bind, fixed container name, global/anonymous volume, secret in argv/service environment/output, host secret file, implicit credential rotation, automatic rollback/down on readiness failure, volume deletion/prune, or destructive cleanup target; paths with spaces/non-ASCII/symlinks and dirty worktrees remain safe

**Scale/Scope**: One project resource set per canonical workspace, exactly three dependency instances, one project network, two named volumes, one advisory lock, three container secret files, one Grafana tmpfs, two PostgreSQL-aware service readiness adapters, two supported host/architecture classes, and no HA/cluster capacity promise

**Affected Components**: Root `Makefile`/`.env.example`; `tools/workflow/` package discovery and `tests/workflow/`; `infra/docker/` and infra tests; `ops/workflow/` plus local environment runbook; new `shared/contracts/repository-workflow/v2/` while v1 stays immutable, plus local-environment contract copies; `services/api-service/` and `services/billing-service/`; repository/infra documentation and ADR 002

**Contracts**: Root Make Workflow v2 versions the breaking dev/dev-down success/side-effect semantics and migration window; workflow event v2 uses required `event_id`, `event_type`, `schema_version`, UTC `timestamp`, `producer`, `correlation_id`, and `payload`, with the payload carrying dependency, `WAITING`, and stable SF02 diagnostics without mutating v1; local dependency manifest/lifecycle v1 owns index plus child digests, URL grammar, collision-safe identity, lock, resources, probes, persistence and recovery; service health v1.1 adds only a 503 dependency-readiness response for API/Billing while endpoint-specific 200/liveness shapes remain exact

**Data & Migrations**: No Alembic revision or schema mutation. API/Billing remain migration owners, but lifecycle never invokes migration. Lock plus exact Compose project identity provides operation idempotency/reconciliation rather than a datastore transaction. Ordinary down preserves all named volumes; PostgreSQL role/password mismatch on an existing volume fails readiness and requires explicit manual recovery, never implicit role mutation. Test-only disposable volumes may be removed only by their isolated fixture teardown.

**Security & Privacy**: Pure action/mode validation precedes identity and all resource access; read-only manifest/runtime/config/port preflight precedes lock-file creation, then endpoint/ownership/ports are revalidated inside the lock before mutation; only `.env.local` supplies lifecycle values and only `127.0.0.1` URLs are accepted; decoded secrets require the injectable-safe `tm_local_` grammar and are passed only in a dedicated Compose child mapping to environment-source secret mounts owned 0400 by verified non-root image UIDs; no host/service environment, argv, event, log or fixture contains values; committed Compose bytes are verified then piped through stdin with a project directory derived only from the project ID so canonical Compose labels cannot reveal the workspace path; the deterministic per-user runtime path rejects symlink/owner/mode drift; unknown ports receive no credentials; Compose/inspect/health output is captured, minimally parsed and redacted; remote Docker endpoint fails closed; index/child digests, licenses and scans cover both platforms

**Observability & Reliability**: One envelope `correlation_id` correlates accessible plain text and JSONL v2 records, and every record has a unique event ID, UTC timestamp, producer and stable event type; every machine-defined dependency payload carries dependency, duration and safe code; pull and readiness clocks are separate, while reconcile plus concurrent probes share one non-extendable 60-second deadline; final snapshots use Compose JSON plus fresh authenticated probes, never stale health; same-project operations are non-blockingly serialized and every losing command immediately returns `OPERATION_IN_PROGRESS`; failure retains inspectable state and named volumes; down reconciles stopped containers/networks and is repeatable without secrets; these local CLI failures are user-visible severity/action states rather than pager alerts, owned by repository/infra/service teams and linked to the runbook; API/Billing liveness remains independent, readiness self-recovers after PostgreSQL returns, and safe probe totals/failures/durations are exposed through existing Prometheus endpoints

**Deployment & Rollback**: No production deployment or image publish. ADR 002 is accepted as a design decision before implementation, while implementation verification remains pending. Rollout is staged: publish v2 contracts/migration notice/failing tests while v1 behavior remains, migrate all consumers, add verified digests/Compose/adapter/readiness plus Linux x86_64 and macOS arm64 lifecycle/security/performance evidence, then atomically activate v2 targets, event envelope, help and recovery documentation and record implementation verification. Rollback is a reviewed revert of manifest/Compose/adapter/v2 activation/service probes together, restoring v1 event plus `SF02_NOT_READY` fail-closed behavior while retaining version history; never delete existing project volumes. Image rollback changes tag/index/child digests and scans together.

## Constitution Check

*GATE: passed before Phase 0 research and re-checked after Phase 1 design.*

### Pre-Research Gate

| Gate | Status | Evidence / Decision |
|------|--------|---------------------|
| Architecture and ownership | PASS | Reuses the approved root workflow and infra boundary; Compose is an adapter, not a service; API/Billing own independent probes; no cross-service imports/storage; significant orchestration decision is recorded in ADR 002 |
| Contracts and compatibility | PASS | Root Make/event v2 explicitly versions the breaking success/side-effect and strict-event changes; event v2 uses the constitution-required standard envelope; v1 Make/event files remain immutable through a documented consumer migration/deprecation window; lifecycle/manifest/health interfaces precede implementation |
| Security and privacy | PASS | Local-only mode/endpoint, loopback literal, strict synthetic grammar, Compose environment-source 0400 secret files for verified non-root UIDs, secure lock paths, redaction and official digest/scan/license review are planned before resources |
| Data correctness | PASS | PostgreSQL/Redis/Grafana durability classes, project ownership, lock/reconciliation, volume retention and no-migration/no-delete rules are explicit; no business data model is introduced |
| Testing | PASS | Unit, contract, fake-subprocess, real compatible dependency, auth/port/concurrency/interruption/persistence, dirty-worktree, terminal accessibility and shared-harness platform/performance tests precede activation |
| Operations | PASS | Liveness/readiness separation, one non-extendable readiness deadline, bounded per-service/outer stop limits, per-dependency redacted envelope events, API/Billing readiness metrics, local no-pager severity rationale, recovery/runbook ownership and platform SLO evidence are defined |
| Delivery | PASS | The independent workflow lock receives the reviewed asyncpg addition while service locks remain unchanged; Docker/Compose/images are exact; CI/local root gates, dependency impact, rollout/revert and traceability are planned |

No exception or temporary waiver is required. ADR 002 changes from Proposed to Accepted as a design approval before lifecycle implementation; implementation verification remains pending until both-platform evidence passes.

### Post-Design Gate

| Gate | Status | Phase 1 evidence |
|------|--------|------------------|
| Architecture and ownership | PASS | [data-model.md](./data-model.md) separates Git facts, developer secrets, project resources, operations and per-service readiness; [ADR 002](../../docs/decisions/002-local-compose-lifecycle.md) records replacement boundaries |
| Contracts and compatibility | PASS | [contracts/](./contracts/) defines Root Make/event v2 standard-envelope migration, lifecycle invocation/config/identity/state/recovery, manifest schema and service health v1.1 before runtime consumers; strict v1 readers migrate before activation |
| Security and privacy | PASS | Lifecycle contract fixes synthetic URL-secret grammar, Compose-owned secret files, secure lock storage, no-credential port checks, remote-context rejection, index/child verification and safe diagnostics; quickstart forbids secret evidence |
| Data correctness | PASS | Data model defines source of truth, lock/reconciliation invariants, persistent/rebuildable/ephemeral classes, no migrations and no deletion; quickstart tests marker retention |
| Testing | PASS | [quickstart.md](./quickstart.md) and the verification matrix cover positive, negative, integration, recovery, concurrency, dirty worktrees, terminal accessibility, shared-harness performance and both host platforms |
| Operations | PASS | Per-dependency health results, fresh-state rule, shared readiness deadline, 60/30 service grace plus 75-second stop bound, workflow v2 standard correlation envelope, API/Billing 503, readiness metrics and failure recovery are contracted |
| Delivery | PASS | Exact runtime/image versions, digest materialization gate, two-platform evidence, staged rollout and fail-closed revert are specified |

Post-design result: **PASS after corrective audit — no unresolved clarification, placeholder design decision, or unjustified constitution violation.** The initial draft's unversioned Make/event change, sequential timeout overflow and host-file/non-root mismatch are closed by v2 migration, a single deadline and Compose environment-source secret ownership. Actual OCI index/child digest values remain an implementation supply-chain artifact: the schema rejects missing identities, and implementation cannot pass the first gate until registry resolution and both-platform verification are committed.

## Project Structure

### Documentation (this feature)

```text
specs/002-local-dependency-lifecycle/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── local-environment-lifecycle.md
│   ├── local-dependency-manifest.schema.json
│   ├── make-workflow-v2.md
│   ├── workflow-event-v2.0.schema.json
│   └── service-health-v1.1.openapi.yaml
├── evidence/
│   ├── README.md                          # Redacted evidence index and ownership
│   ├── quality-gates.md
│   ├── linux-amd64.md
│   ├── macos-arm64.md
│   └── developer-usability.md
└── tasks.md                              # Created later by /speckit-tasks
```

### Source Code (repository root)

```text
Makefile                                  # Stable dev/dev-down delegation and updated help only
.env.example                              # SF02 fields, comments and unusable placeholders
AGENTS.md                                 # Active feature context
docs/decisions/
└── 002-local-compose-lifecycle.md         # Accepted before implementation merge
tools/workflow/
├── pyproject.toml                        # Discover workflow plus workflow.local_env packages
├── cli.py                                # Replace only SF02 transition dispatch
├── events.py                             # Event v2 emitter/codes/redaction
├── security.py                           # Reuse/extend strict safe config primitives
└── local_env/
    ├── __init__.py
    ├── models.py                         # Typed internal entities/states
    ├── config.py                         # .env.local and URL validation/derivation
    ├── identity.py                       # Canonical path hash and fcntl lock
    ├── compose.py                        # Verified-stdin/safe-project-dir Compose JSON adapter
    ├── probes.py                         # PostgreSQL/Redis/Grafana safe probes
    └── lifecycle.py                      # Ordered dev/dev-down orchestration
tests/workflow/
├── test_sf02_transition.py               # Becomes transition-replacement compatibility tests
├── test_local_env_config.py
├── test_local_env_identity.py
├── test_local_env_events.py
├── test_local_env_compose.py
├── test_local_env_lifecycle.py
├── test_local_env_concurrency.py
├── test_local_env_security.py
├── test_local_env_dirty_worktree.py
├── test_local_env_performance.py
├── test_accessibility_performance.py      # Extend SF01 terminal accessibility coverage
└── test_local_env_integration.py          # Isolated real Compose projects only
infra/
├── docker/
│   ├── compose.local.yml                 # Exactly postgres/redis/grafana
│   └── README.md
└── tests/
    └── test_local_compose.py             # Structure, digest, bind, volume, secret tests
ops/
├── workflow/
│   ├── toolchains.json                   # Compose + current image integrity sources
│   └── local-dependencies.json           # Runtime manifest; no secret/placeholder digest
└── runbooks/
    └── local-environment.md               # Safe inspect/recovery/moved-workspace guide
shared/contracts/
├── repository-workflow/v1/
│   ├── make-workflow.md                  # Immutable SF01 fail-closed history
│   ├── workflow-event.schema.json        # Immutable 1.0.0 history
│   └── service-health.openapi.yaml       # Health-only minor 1.1.0
├── repository-workflow/v2/
│   ├── make-workflow.md                  # Breaking SF02 activation/migration
│   └── workflow-event.schema.json        # 2.0.0
└── local-environment/v1/
    ├── lifecycle.md
    └── local-dependency-manifest.schema.json
services/
├── api-service/
│   ├── app/
│   │   ├── main.py                       # Lifespan-owned engine/probe
│   │   ├── health.py                     # 200/503 contract adapter
│   │   ├── database.py                   # Owned async SELECT 1 probe
│   │   └── observability.py              # Safe readiness counters/histogram
│   └── tests/
│       ├── test_health.py
│       ├── test_database_readiness.py
│       └── test_readiness_metrics.py
└── billing-service/
    ├── app/{main.py,health.py,database.py,observability.py}
    └── tests/{test_health.py,test_database_readiness.py,test_readiness_metrics.py}
```

**Structure Decision**: Keep orchestration in the maintained repository workflow package and declarative resources in `infra/`; update setuptools discovery so `workflow.local_env` is included in installed/locked execution; store reviewed environment facts in `ops/workflow/` and reusable interfaces in versioned `shared/contracts/`. API/Billing duplicate only a small owned probe adapter so neither service imports the other's implementation. No new service, datastore, shared business package, public script, Compose override, or destructive command is introduced.

## Implementation Strategy

### Phase A — Contract materialization, ADR acceptance, and failing tests

1. Accept ADR 002 as the approved design before lifecycle implementation, mark implementation verification pending, and link it from infra/runbook/traceability docs.
2. Copy Root Make/event v2 standard-envelope, lifecycle/manifest and health contracts into versioned runtime locations while leaving v1 Make/event artifacts immutable; publish the activation/deprecation notice and keep executable `SF02_NOT_READY` behavior during this phase.
3. Enumerate every repository-owned event consumer and add migration tests that first fail on missing v2 support; separately add the future lifecycle tests while preserving target names and pure mode-before-lock safety ordering.
4. Add manifest/Compose structural negative fixtures for tag-only/latest/missing index-or-child identity, extra services, wildcard ports, `container_name`, global/anonymous/deleted volumes, embedded/service-environment secrets, missing healthchecks and missing Grafana tmpfs.
5. Resolve the three official exact tags to real OCI index/child digests, verify both native architectures, capture license/scan evidence, and commit `ops/workflow/local-dependencies.json`; update the existing PostgreSQL 15.12 placeholder integrity reference as one reviewed dependency change.

**Exit evidence**: Contracts validate; ADR is accepted; tests fail only for missing runtime behavior; no placeholder digest or unsafe Compose form can pass `contracts-check`/infra tests.

### Phase B — Pure configuration, identity, event, and lock core

1. Add typed models/state transitions and tests before implementation.
2. Implement pure Make-mode-origin validation first, then `.env.local` parsing, strict `tm_local_` decoded-secret grammar, URL/port derivation and field-name-only errors.
3. Implement canonical physical path + NFC + UTF-8 SHA-256 short ID plus full fingerprint with spaces/Chinese/symlink/case/different-worktree/move/collision fixtures; prove no path in output or any custom/Compose-canonical resource metadata.
4. Implement the deterministic secure per-user/project runtime base, empty Compose project directory and non-blocking `fcntl` boundary; reject symlink/type/owner/mode drift and prove contention plus abnormal holder exit.
5. Add `workflow.local_env` to setuptools package discovery and asyncpg 0.30.x to the independent workflow lock without changing service locks. Implement event v2 standard-envelope emitter/schema/consumer support with unique event IDs, UTC timestamps, producer/type/correlation fields, dependency-phase payload requirements and broader redaction while keeping v1 Make/event artifacts and tests immutable through activation.

**Exit evidence**: Pure unit/contract suites pass without Docker; rejected preflight cases create no Docker/socket/config or coordination artifact; only the verified secure runtime directory, Compose project directory and lock file may exist after preflight passes and lock acquisition begins; v1 regression and v2 consumer-migration suites both pass.

### Phase C — Compose definition and safe runtime adapter

1. Add `compose.local.yml` with exactly three index-digest images, canonical service names, project-scoped default network, long-syntax `127.0.0.1` ports, PostgreSQL/Redis named volumes, explicit 0700 runtime-UID/GID-owned Grafana `/var/lib/grafana` tmpfs, authenticated healthchecks, verified upstream non-root UIDs and 60/30/30 stop grace periods.
2. Implement top-level environment-source Compose secrets and long-syntax 0400 UID/GID targets for PostgreSQL/Grafana passwords and the single-directive Redis config; use a dedicated child mapping and prove values never enter argv, service environment, Compose model output, inspect snapshots, host files or worktree.
3. Implement the Compose adapter with fixed global arguments, committed-blob equality checks, verified YAML bytes over `-f -`, a safe runtime project directory, captured JSONL `ps`, minimal inspect fields, pull/up/down commands, local endpoint/platform/capability verification and unknown-field-tolerant parsing. Reject a dirty/replaced/symlink Compose asset and scan all resulting canonical labels for the raw/canonical workspace path.
4. Implement project short-ID/full-fingerprint ownership checks, fail-closed collision handling, mandatory read-only old-resource reporting, exact-owned non-current image replacement with volume preservation, publisher checks and bind-only port preflight/race mapping.
5. Add fake CLI tests for exact argument ordering, no `-v`/prune/image removal, missing config down, remote context rejection, malformed JSON, redaction and interrupted subprocesses.

**Exit evidence**: Infra/adapter suites prove the desired model before any real dependency test; no secret or raw Docker error survives serialization.

### Phase D — Lifecycle orchestration and real dependency evidence

1. Implement `dev` phases as read-only preflight → acquire secure lock → revalidate endpoint/ownership/ports → child secret mapping → missing-only pull → index/child digest verification → one 60-second deadline → `up --detach --pull never` → concurrent current-state/authenticated probes using only remaining time → aggregate; every mutable phase stays under the lock.
2. Implement PostgreSQL authenticated TCP `SELECT 1`, Redis AUTH/PING with `REDISCLI_AUTH`, and Grafana health/admin probes with per-attempt remaining-time bounds, no post-deadline success and safe result categories.
3. Implement healthy fast path, stopped/stale/partial reconciliation, timeout state retention, interrupt/daemon-loss retry, and exact-project moved-workspace reporting.
4. Implement `dev-down` without config, safe parse-only child secrets, no-container/network `already stopped` rule, exact-project `down --remove-orphans` with no CLI timeout override, declared 60/30/30 service grace, 75-second outer bound, precise fallback and post-stop/volume verification.
5. After the v2 consumer migration gate passes, complete an activation-candidate dev/dev-down dispatch and event-v2 envelope path in `cli.py` behind the existing fail-closed activation guard; do not remove the public runtime `SF02_NOT_READY` behavior in this phase.
6. Run isolated real Compose tests for cold/pulled image phases, ten repeated starts, ten start/down/restart cycles, PostgreSQL marker retention, empty Redis, zero Grafana anonymous volumes, wrong auth/config injection, port conflict/race, partial/unhealthy/stopped state, deadline edge, forced interrupt, lock conflict, hash collision and two-workspace isolation. A short-lived test-only container attached to the exact project network receives synthetic probe material over stdin and performs a PostgreSQL query, Redis AUTH/PING and Grafana health/admin HTTP calls against the three canonical service URLs; DNS resolution alone is insufficient.

**Exit evidence**: All lifecycle success criteria except service readiness and cross-host performance pass on Linux x86_64 through the guarded candidate adapter; fixture cleanup cannot address a developer project ID, and public targets remain fail-closed.

### Phase E — API/Billing dependency-aware readiness

1. Update the shared health OpenAPI to v1.1 before changing service behavior.
2. In each service, write failing tests for liveness independence, 200 ready, 503 invalid-config/connection/auth/query/timeout, safe payload/logs, recovery without restart, two-second bound, and secret-free Prometheus probe-total/failure/duration metrics.
3. Add a lifespan-owned SQLAlchemy async engine/probe using existing locked dependencies and `pool_pre_ping`; safely map the lifecycle `postgresql://` URL to asyncpg internally and dispose on shutdown.
4. Inject the probe through application state/test dependencies; keep successful response fields unchanged, emit the contracted single PostgreSQL result only on 503, and update service-owned low-cardinality readiness counters and duration histograms for success, failure and recovery.
5. Run real PostgreSQL probe integration for API and Billing independently. Confirm Gateway/Admin source/tests/contracts did not gain dependency probes and no business route was added.

**Exit evidence**: Health contract tests and real query/recovery tests pass; liveness stays 200 during PostgreSQL outage and readiness recovers to 200 without service restart.

### Phase F — Documentation, platform matrix, and rollout gate

1. Update `.env.example`, root/infra/service docs and `ops/runbooks/local-environment.md` with configuration, service names, project/move semantics, safe addresses, data/stop effects, diagnostics, secret-safe inspection and recovery.
2. Add and run explicit terminal accessibility plus dirty-worktree preservation tests, then run full `make lint`, `make test`, `contracts-check`, security/secret checks and structural link validation; verify `NO_COLOR`/plain-text/screen-reader semantics, unchanged dirty tracked/untracked files, no tracked/host secret file, missing digest identity, package-discovery omission or lock drift.
3. Implement one deterministic performance harness used unchanged on both platforms. On Linux x86_64, execute its predeclared 20-trial cold-start batch with images already verified, no project container/network and fresh isolated test-owned volumes for each trial; count every valid trial and require at least 19 of 20 to reach all three ready states within 60 seconds. Also record native image variants, ten repeat timings, signals, ten-cycle persistence and all failure suites in CI.
4. On representative macOS arm64, repeat the same 20-trial/19-pass algorithm plus native variant, path/NFC, Desktop loopback, Compose secret ownership, health, stop and ten-repeat ≤15-second evidence; compare event v2 behavior with Linux. A prerequisite/toolchain failure invalidates and reruns the whole declared batch rather than excluding a slow trial.
5. The repository workflow owner schedules and executes [quickstart.md](./quickstart.md) with 10 representative developers who have not previously used SF02, using the committed evidence template and participant criteria. Starting from a prerequisite-ready checkout, allow only root help and the local-environment documentation; require at least 9 of 10 independently to prepare config, start, confirm three states and locate one injected-failure recovery instruction within 10 minutes. Attach only redacted aggregate evidence.
6. Only after both platform reports, accessibility/security/dirty-worktree gates, consumer migration, documentation and lifecycle evidence pass, atomically remove `SF02_NOT_READY`, activate dev/dev-down plus event v2 and matching help/recovery text, and mark ADR implementation verification and feature completion without changing its already-Accepted design status.

**Exit evidence**: Both platforms meet the same functional/output contract and their separately calculated performance targets; public v2 activation is atomic; ADR/PR documents design acceptance separately from implementation verification plus dependency, contract, schema/security impact, rollout and volume-preserving rollback.

## Verification Matrix

| Requirement area | Planned automated evidence | Manual/review evidence |
|------------------|----------------------------|------------------------|
| US1 / FR-001–015 | Target compatibility; strict preflight; manifest/digest; pull/readiness clock split; port conflict; real probes; cold/repeat/partial/retry tests | Safe output, host addresses, ≤60s/≤15s evidence per platform |
| US2 / FR-016–023 | Identity/path/worktree/move/collision fixtures; raw/canonical path absence from all custom and Compose canonical labels; exact fingerprint ownership; no-config down including stopped resources; ten persistence cycles; zero anonymous/deleted volumes; secure lock/concurrency/abnormal-exit tests | Old-resource recovery wording and PostgreSQL marker retention review |
| US3 / FR-007–012, FR-024–026 | URL/derived address and secret-grammar tests; test-only project-network PostgreSQL query, Redis AUTH/PING and Grafana authenticated HTTP probes; event v2 standard-envelope schema/migration; API/Billing exact 200/503/recovery shapes plus safe readiness metrics; Gateway/Admin non-change assertion | Runbook usability and 10-person new-developer exercise with ≥9/10 in ten minutes |
| FR-027–029 | Subprocess denylist/snapshots; runtime lockfile immutability and reviewed implementation-lock change checks; dirty tracked/untracked worktree before/after test; same Compose definition and native image platform checks | macOS arm64 + Linux x86_64 matrix comparison |
| ER-001–003 | Contract version/drift tests; secret/remote/wildcard/argv scans; volume/schema/migration negative assertions | Digest/license/security review and rollback identity |
| ER-004–007 | Shared deterministic performance harness; per-phase monotonic timing; idempotency/concurrency/interruption; redacted standard-envelope JSONL; service readiness metrics; plain text/NO_COLOR/non-interactive output; graceful stop tests | Separate host performance reports and screen-reader/plain-text review |
| SC-001–009 | Per-platform 20 cold trials with ≥19/20 ≤60s, ten repeat/cycle runs, real isolated connection probes, all named negative fixtures, two-workspace isolation and 100 concurrent conflicts | Ten representative new developers with ≥9/10 in ten minutes plus evidence checklist |

## Test-First Order

For every slice, the behavior test/contract change lands before its implementation:

1. Runtime contract copies, manifest and Compose structural fixtures.
2. Immutable Make/event v1 regression plus event v2 standard-envelope migration, identity/timestamp/producer/correlation, payload dependency and diagnostic schema tests.
3. Configuration/URL/secret-redaction pure tests.
4. Identity, ownership, lock and moved-workspace pure tests.
5. Fake Compose command/order/JSON/error/interrupt tests.
6. Real image, network, health, persistence, stop and retry tests.
7. Concurrency and cross-workspace isolation tests.
8. API/Billing fake-probe health contract tests.
9. API/Billing real PostgreSQL query/recovery and readiness metric tests.
10. Dirty-worktree and terminal accessibility regressions.
11. Shared-harness Linux/macOS performance and quickstart acceptance.

Changed Python workflow/service packages require at least 80% line coverage. Negative assertions directly cover configuration trust, secret disclosure, ownership, concurrency, idempotency, timeouts, data retention, forbidden migration/cleanup and rollback safety.

## Rollout and Rollback

### Rollout

1. Accept ADR 002 as a design decision, then merge Root Make/event v2 contracts, migration notice, manifest schema and failing tests while runtime behavior remains v1 `SF02_NOT_READY`; keep ADR implementation verification pending.
2. Resolve/scan/commit real three-image multi-platform digests; reject any unsupported architecture or placeholder before Compose use.
3. Land pure workflow core and Compose adapter behind tests while dev/dev-down still fail closed.
4. Migrate all enumerated repository consumers and complete the guarded activation candidate while public dev/dev-down still return `SF02_NOT_READY`.
5. Add API/Billing readiness and safe probe metrics after shared health v1.1 is materialized.
6. Require accessibility, dirty-worktree, security, Linux x86_64 CI and representative macOS arm64 evidence before public activation; record the shared performance harness and redacted evidence.
7. Atomically switch dev/dev-down from `SF02_NOT_READY`, make the event-v2 envelope default, publish matching help/recovery text, announce the activation/deprecation window, Grafana tmpfs state, PostgreSQL credential-drift recovery and workspace move/collision semantics, then mark ADR implementation verification and feature completion. Retain v1 artifacts through the next tagged release.

### Rollback

- Revert via reviewed PR; never reset/force-push or delete local volumes.
- Revert Compose asset, dependency manifest, workflow adapter, event/health contracts, API/Billing probes, tests and docs as one compatible set.
- If safe lifecycle cannot be restored promptly, reinstate the SF01 `SF02_NOT_READY` pre-config/pre-Docker failure instead of reporting false success.
- Leave project-scoped PostgreSQL/Redis volumes untouched for a forward fix; rollback has no destructive cleanup step.
- Roll back an image by committing its prior tag + index digest + both child digests + scan/license evidence together.
- If a real secret is exposed, revoke/rotate and audit first; lifecycle rollback does not rewrite history or silently mutate the PostgreSQL role.

## Complexity Tracking

No constitution violation or temporary exception is planned. The `tools/workflow/local_env/` package is justified by the feature's independent configuration, identity/lock, Docker adapter, probe and orchestration boundaries; it remains an internal adapter under the existing workflow component, not a new runtime service. Two small service-owned database probes intentionally avoid a cross-service implementation dependency.
