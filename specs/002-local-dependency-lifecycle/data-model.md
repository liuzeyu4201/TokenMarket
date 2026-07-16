# Data Model: 本地依赖环境生命周期

**Feature**: `002-local-dependency-lifecycle`
**Date**: 2026-07-15
**Persistence model**: Git-tracked dependency definitions plus project-scoped Docker resources and ephemeral health/operation evidence; no TokenMarket business schema

## Overview

```text
LocalDependencyManifest 1 ── 3 LocalDependencyDefinition
            │                         │
            │                         ├── 1 DerivedConnection
            │                         └── 0..1 NamedVolumeDefinition
            │
LocalEnvironmentConfiguration 1 ── 3 DerivedConnection
            │
            └── 1 ProjectResourceSet ── 3 DependencyInstance
                         │                       │
                         ├── 1 LifecycleLock    └── * DependencyHealthResult
                         ├── 0..1 LifecycleOperation ── * WorkflowEvent
                         └── * ComposeSecretMaterial

api-service     1 ── * ServiceReadinessResult(postgres) ── 1 ServiceReadinessMetrics
billing-service 1 ── * ServiceReadinessResult(postgres) ── 1 ServiceReadinessMetrics
```

Definitions are repository-owned and version controlled. Real local configuration and in-memory secret material are developer-owned and never tracked. Docker resources are local mutable state. Health/readiness results and workflow events are short-lived evidence and cannot be reused as current truth after a new operation or daemon restart.

## Entity: LocalDependencyManifest

Repository-owned source of truth for the SF02 dependency set and lifecycle constants.

| Field | Type | Rules |
|-------|------|-------|
| `schema_version` | semantic version | `1.0.0` for the first SF02 manifest |
| `diagnostic_contract_version` | semantic version | `2.0.0`; Root Make/event v2 activation |
| `project` | object | `prefix=tokenmarket`; SHA-256 canonical NFC UTF-8 path; 12-char project suffix plus 64-char collision fingerprint; committed Compose bytes via stdin, secure runtime project directory, and POSIX lock mechanism |
| `runtime` | object | Docker `29.5.3`, Compose `5.1.4`, local Unix endpoint, environment-source Compose secret files, and ordered hosts `darwin/arm64`, `linux/amd64` |
| `timeouts` | object | Readiness `60`, healthy repeat `15`, complete stop operation `75` seconds |
| `dependencies` | ordered list | Exactly `postgres`, `redis`, `grafana`; no optional fourth dependency |

**Invariants**:

- Manifest validation and digest/platform verification occur before Compose creates or modifies resources.
- A version/digest/license/platform change is a reviewed dependency contract change and updates ADR/scan evidence.
- No field contains a real URL password, Grafana administrator password, absolute workspace path, production address, or user data.

**Owner/source of truth**: Repository/infra maintainers; planned runtime path `ops/workflow/local-dependencies.json`, validated by `contracts/local-dependency-manifest.schema.json`.

## Entity: LocalDependencyDefinition

Defines one and only one required dependency.

| Field | Type | Rules |
|-------|------|-------|
| `id` | enum | `postgres`, `redis`, `grafana` |
| `repository` | OCI repository | Official/Verified Publisher allowlist only |
| `version_tag` | exact tag | PostgreSQL `15.18-bookworm`; Redis `7.2.14-bookworm`; Grafana `13.0.3` |
| `index_digest` | OCI SHA-256 | `sha256:` + 64 lowercase hex; real value required, placeholders rejected |
| `platform_digests` | object | Exact `linux_amd64` and `linux_arm64` child digests |
| `required_platforms` | ordered tuple | Exactly `linux/amd64`, `linux/arm64` in schema order |
| `service_name` | enum | Same as `id`; stable container-network DNS name |
| `host_url_field` | enum | `DATABASE_URL`, `REDIS_URL`, `GRAFANA_URL` respectively |
| `container_port` | integer | 5432, 6379, 3000 respectively |
| `default_host_port` | integer | Same default values; actual host port comes only from URL |
| `host_bind_address` | IP literal | Exactly `127.0.0.1` |
| `liveness_probe` | enum | Container/process state plus dependency-specific low-risk probe |
| `readiness_probe` | enum | Authenticated, side-effect-free expected result |
| `durability` | enum | `durable-fact`, `preserved-rebuildable`, `ephemeral` |
| `secret_transport` | enum | PostgreSQL password file, Redis config file, or Grafana password file |
| `volume` | optional object | Required named volumes for PostgreSQL/Redis; absent for Grafana |
| `ephemeral_storage` | optional object | Required Grafana tmpfs at `/var/lib/grafana`, mode 0700, owned by its verified runtime UID/GID; absent for PostgreSQL/Redis |
| `stop_grace_period_seconds` | positive integer | PostgreSQL 60; Redis/Grafana 30 |
| `runtime_uid`, `runtime_gid` | positive integer | Verified from each pinned target image and used as secret-file owner |
| `runtime_uid_policy` | enum | `verified-upstream-non-root-secret-owner`; effective PID 1 and secret access tested |

**Dependency invariants**:

- `image_ref = repository + ":" + version_tag + "@" + index_digest`; tag-only, missing child-digest maps and leaf-only identities are invalid.
- PostgreSQL final readiness requires authenticated TCP `SELECT 1` against the configured database.
- Redis final readiness requires AUTH + `PING` → `PONG` on one connection.
- Grafana final readiness requires health database `ok` and authenticated server-admin identity.
- No definition depends on another dependency. No Kafka, Prometheus, Loki, MinIO, frontend, or business service appears.

## Entity: LocalEnvironmentConfiguration

Developer-owned real local configuration parsed from ignored `.env.local` only for `make dev`.

| Field | Type | Classification | Validation |
|-------|------|----------------|------------|
| `MODE` | enum | public local metadata | Exactly `local`; cannot select effective mode |
| `DATABASE_URL` | URL | secret | PostgreSQL grammar, user/password/database present, host `127.0.0.1`; decoded password matches local-secret grammar |
| `REDIS_URL` | URL | secret | Redis default user/password/db present, host `127.0.0.1`; decoded password matches local-secret grammar |
| `GRAFANA_URL` | URL | internal | HTTP, no user-info, root path only, host `127.0.0.1` |
| `GRAFANA_ADMIN_PASSWORD` | string | secret | Matches `^tm_local_[A-Za-z0-9_-]{32,96}$` |

**Invariants**:

- Three ports are valid and pairwise distinct.
- Query strings, fragments, non-loopback hosts, empty/working defaults, test/prod markers and production-looking hosts are rejected.
- Percent-decoding occurs only after syntax validation; every secret must match `^tm_local_[A-Za-z0-9_-]{32,96}$`, excluding control/config syntax, and is never placed in messages, exceptions, snapshots or events.
- Shell variables do not override lifecycle configuration. `.env.local` cannot elevate the command's effective mode.
- `make dev-down` neither requires nor validates this entity.

**Retention**: Ignored developer file; may be rotated/deleted at any time. PostgreSQL credential rotation for an existing volume is not performed implicitly by SF02; mismatch fails readiness and uses an explicit recovery procedure.

## Entity: DerivedConnection

Immutable in-memory projection created from a validated host URL.

| Field | Type | Rules |
|-------|------|-------|
| `dependency_id` | enum | One dependency |
| `host_scheme` | string | Validated dependency scheme |
| `host_address` | string | `127.0.0.1` only |
| `host_port` | integer | URL-derived |
| `container_host` | enum | `postgres`, `redis`, `grafana` |
| `container_port` | integer | Definition-derived, never user-overridden |
| `container_url` | URL | Preserve scheme/user-info/path; replace host/port with service name/container port |
| `username` | optional string | PostgreSQL/Redis validated value |
| `secret` | optional secret string | Held only long enough to create the dedicated Compose child mapping or a bounded probe environment |
| `database` | optional string/int | PostgreSQL database or Redis DB number |

**Invariant**: This projection is not serialized to logs/events. Only a safe host address such as `postgresql://127.0.0.1:5432/tokenmarket` with user-info removed may be displayed.

## Entity: ProjectResourceSet

All local resources owned by one canonical workspace identity.

| Field | Type | Rules |
|-------|------|-------|
| `workspace_hash` | 12-char hex | Recomputed from workspace root; never accepted from local config |
| `workspace_fingerprint` | 64-char hex | Same SHA-256 in full; collision/ownership label, never raw path |
| `project_id` | string | `tokenmarket-<workspace_hash>` |
| `labels` | map | Exact repository, short workspace ID and full fingerprint; custom labels contain no path, Compose canonical labels may contain only the safe runtime directory and never the workspace path |
| `containers` | set | At most one per required service |
| `network` | set | At most one project-scoped default network while running |
| `named_volumes` | set | PostgreSQL and Redis volumes only; preserved across ordinary down |
| `runtime_directory` | host path handle | Deterministic secure per-user/project base; contains the 0600 lock and empty 0700 Compose project directory, no secret/raw workspace path, and is not emitted |
| `current_operation` | optional reference | At most one lock-holding lifecycle operation |

**Invariants**:

- State mutation is authorized by exact `project_id` plus full fingerprint, not a prefix-label query.
- A short-hash collision is detected by fingerprint mismatch and fails before mutation; different workspaces never share containers, network, or named volumes. Sharing immutable daemon image cache is allowed.
- Workspace move creates a new entity. Matching repository-prefix resources with a different workspace ID must be reported with recovery direction and are never adopted/stopped automatically.
- Compose receives only verified committed YAML bytes through stdin and a project directory derived from `project_id`. Tests scan every Docker/Compose label and reject the raw or canonical workspace path in any resource metadata.
- Ordinary down removes containers/orphans and temporary network, preserves all named volumes, and never uses prune.

## Entity: LifecycleLock

| Field | Type | Rules |
|-------|------|-------|
| `key` | string | Project ID only |
| `mechanism` | enum | POSIX advisory `fcntl.flock` |
| `mode` | enum | Non-blocking exclusive |
| `holder_operation` | enum | `dev` or `dev-down` |
| `acquired_at` | monotonic timestamp | Internal timing only |
| `storage_safety` | invariant | Secure per-user base, no symlink following, regular current-user 0600 file |

**State transition**:

```text
available ── LOCK_EX|LOCK_NB success ──> held ── normal/exception/process exit ──> available
    └──── lock contention ─────────────> rejected(OPERATION_IN_PROGRESS)
```

The empty lock file may remain; kernel lock state is authoritative. No PID-based stale recovery is needed.

## Entity: LifecycleOperation

Represents one `make dev` or `make dev-down` run.

| Field | Type | Rules |
|-------|------|-------|
| `correlation_id` | UUID/string | Stable lifecycle-run correlation ID in every emitted envelope; each envelope has a separate unique event ID |
| `action` | enum | `dev`, `dev-down` |
| `project_id` | string | Safe to display |
| `phase` | enum | `identity`, `lock`, `preflight`, `image-pull`, `image-verify`, `reconcile`, `liveness`, `readiness`, `stopping`, `final` |
| `status` | enum | `REQUESTED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `INTERRUPTED`, `REJECTED` |
| `started_at` | monotonic timestamp | Used for bounded budgets |
| `readiness_started_at` | optional monotonic timestamp | Set only after all images verified |
| `readiness_deadline` | optional monotonic timestamp | Exactly start + 60 seconds; reconcile, probes and retries use remaining time |
| `duration_ms` | non-negative integer | Per phase and aggregate |
| `diagnostic_code` | stable enum | From workflow event v2.0 |

**Start state machine**:

```text
REQUESTED
  └─ pure mode + identity/fingerprint + read-only manifest/runtime/config/port preflight valid
       └─ secure runtime directory/lock acquired + state revalidated
            ├─ endpoint/ownership/port drift ──> FAILED (no mutable action)
            └─ IMAGE PHASE
                 ├─ pull/digest failure ──> FAILED (no project instance created)
                 └─ IMAGES_AVAILABLE
                      └─ RECONCILING/STARTING
                           ├─ all live + authenticated ready ──> READY/SUCCEEDED
                           ├─ bounded wait ──> FAILED (resources retained)
                           └─ interrupt/runtime loss ──> INTERRUPTED (retriable)
```

**Stop state machine**:

```text
REQUESTED ── identity/lock ──> DISCOVERING
  ├─ no exact-project container/network (volumes may remain) ──> SUCCEEDED (already stopped)
  └─ STOPPING ── graceful down ──> containers/network absent + volumes retained ──> SUCCEEDED
                  └─ timeout/runtime loss ──> FAILED (remaining state reported, volumes retained)
```

## Entity: DependencyInstance

Observed reconciled state of one definition in a project.

| Field | Type | Rules |
|-------|------|-------|
| `dependency_id` | enum | Required dependency |
| `container_id` | optional opaque ID | Read from Compose JSON; never used without project/service verification |
| `image_digest` | OCI digest | Must equal manifest index/selected platform identity |
| `image_matches_desired` | boolean | Compare the exact observed digest to the already verified desired index/current-platform child identity after owner checks |
| `state` | enum | `ABSENT`, `CREATED`, `RUNNING`, `STOPPING`, `EXITED`, `UNKNOWN` |
| `health` | enum | `UNKNOWN`, `STARTING`, `HEALTHY`, `UNHEALTHY` |
| `published_port` | integer | Must match URL-derived host port |
| `owner_labels_valid` | boolean | Required before mutation/reuse |
| `volume_attached` | boolean | PostgreSQL/Redis only |

**Reconciliation**:

- Exact matching healthy instance is reused.
- Missing/stopped instance is converged with `up`; stale health is ignored.
- Wrong project/fingerprint/owner labels fail `RESOURCE_OWNERSHIP_CONFLICT`; they are never adopted.
- After desired index/child identities are verified, any exact-owned container whose image does not match the desired identity is replaceable by Compose and its declared named volume is preserved. There is no historical-image allowlist or ambiguous reviewed/unknown revision state; ownership mismatch still fails closed.
- A healthy repeated start must not increase container/network/volume counts.

## Entity: DependencyHealthResult

Short-lived evidence for one probe.

| Field | Type | Rules |
|-------|------|-------|
| `dependency` | enum | `postgres`, `redis`, `grafana` |
| `liveness` | enum | `alive`, `not_alive`, `unknown` |
| `readiness` | enum | `ready`, `not_ready`, `waiting` |
| `probe` | enum | `postgres-query`, `redis-auth-ping`, `grafana-health`, `grafana-admin` |
| `checked_at` | UTC timestamp | Evidence only |
| `duration_ms` | non-negative integer | Per probe |
| `code` | stable diagnostic | `OK` or safe failure category |
| `safe_reason` | string | Bounded, redacted, no raw dependency output |

**Freshness rule**: A result is valid only for its operation snapshot. New lifecycle execution, container restart/replacement, daemon restart, or configuration change invalidates it.

## Entity: ComposeSecretMaterial

| Field | Type | Rules |
|-------|------|-------|
| `project_id` | string | Owner key; not part of the secret value |
| `purpose` | enum | `postgres-password`, `redis-config`, `grafana-admin-password`, `teardown-placeholder` |
| `source` | enum | Dedicated Compose child-process environment mapping only |
| `container_file_mode` | octal | 0400 through environment-source secret long syntax |
| `container_owner` | UID/GID | Verified non-root values from pinned image manifest |
| `source_field` | config field name | Name only, never value |
| `lifecycle` | enum | Mapping reference is operation-only; Compose-mounted file exists only with its container |
| `cleanup_state` | enum | `in-memory`, `released`, `container-removed` |

Secret bytes are excluded from equality, repr, exceptions, event serialization, test snapshots and diagnostic logs. They are never service environment variables, command arguments, host files, named volumes or image layers. Teardown placeholders match syntax but are not working credentials.

## Entity: LocalPersistentData

| Field | Type | Rules |
|-------|------|-------|
| `owner_project_id` | string | Project-scoped |
| `dependency` | enum | PostgreSQL or Redis |
| `volume_id` | safe logical name | Derived through Compose project scope |
| `durability` | enum | PostgreSQL `durable-fact`; Redis `preserved-rebuildable` |
| `schema_owner` | enum | API/Billing migrations for PostgreSQL; none for Redis |
| `deletion_policy` | enum | `not-supported-by-sf02` |

SF02 creates no business table, applies no Alembic revision, seeds no data, changes no role password on an existing volume, and defines no public destructive cleanup operation.

## Entity: ServiceReadinessResult

API/Billing operational response projection.

| Field | Type | Rules |
|-------|------|-------|
| `service` | enum | `api-service`, `billing-service` |
| `status` | enum | `ready`, `not_ready` |
| `version` | string | Existing SF01 field |
| `request_id` | string | Existing correlation field |
| `dependencies` | list | Present only in 503 response; exactly one PostgreSQL result in SF02 |
| `http_status` | enum | 200 when ready, 503 when not ready |

Liveness is a separate result and never evaluates this entity. A failed result contains only `name=postgres`, `status=not_ready`, and a stable safe code; it never includes URL, username, database exception, SQL, or password.

## Entity: ServiceReadinessMetrics

Each API/Billing process owns an in-memory Prometheus projection of its PostgreSQL readiness probe behavior.

| Field | Type | Rules |
|-------|------|-------|
| `tokenmarket_postgres_readiness_probes_total` | monotonic counter | Increment once for every completed readiness probe attempt |
| `tokenmarket_postgres_readiness_probe_failures_total` | monotonic counter | Increment once for every invalid-config, connection, authentication, query, or timeout result |
| `tokenmarket_postgres_readiness_probe_duration_seconds` | histogram | Observe every completed probe duration, including failures, using repository-approved bounded buckets |

Metrics contain no URL, username, database, exception, SQL, password, workspace, or other unbounded label. Recovery increments the total counter without incrementing the failure counter and produces a new duration observation.

## Entity: WorkflowEvent v2.0

Breaking replacement for strict SF01 v1 readers, activated only after the documented consumer migration gate.

| Field | Type | Rules |
|-------|------|-------|
| `event_id` | UUID | Unique for every emitted envelope, including multiple steps in one lifecycle run |
| `event_type` | const | `workflow.step` |
| `schema_version` | const | `2.0.0` |
| `timestamp` | UTC date-time | RFC 3339 emission timestamp |
| `producer` | const | `repository-workflow` |
| `correlation_id` | string | Same lifecycle-run identifier across every envelope in one command |
| `payload` | object | Strict workflow-step payload; no additional fields |
| `payload.action`, `payload.component`, `payload.phase` | existing semantics | Moved from the v1 root into the v2 payload |
| `payload.dependency` | optional enum | New; one of the three dependencies |
| `payload.status` | enum | Existing values plus `WAITING` |
| `payload.code` | enum | Existing stable codes plus SF02 diagnostic categories |
| `payload.duration_ms`, `payload.message` | existing semantics | Safe, bounded, non-secret |

Events are ordered by emission within one `correlation_id`. Machine-defined dependency lifecycle phases and dependency-specific failure codes require `payload.dependency`. `WAITING`/`PASSED` use `payload.code=OK`; `FAILED`/`SKIPPED` cannot use `OK`; v1's permissive `STARTED` code semantics are not narrowed. Partial dependency success never makes the aggregate `PASSED`.

## Data, migration, backup, and deletion decision

- **Business schema**: None added or changed.
- **Alembic**: Not invoked by `dev`/`dev-down`; existing migration owner rules remain unchanged.
- **Transaction/idempotency**: Lifecycle state changes are serialized by lock and reconciled by exact project identity; there is no database transaction spanning Docker operations.
- **Backup/restore**: SF02 does not back up local data. Ordinary down preserves PostgreSQL volume; recovery is retry/reconciliation, not implicit restore.
- **Deletion**: No developer-facing destructive operation. Test fixtures may delete only their own test-labeled disposable resources during test teardown.
- **Reconciliation**: Current Docker `ps/inspect` snapshot and authenticated probes override cached/stale health evidence.
