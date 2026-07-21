# Contract: Local Dependency Environment Lifecycle

**Version**: 1.0.0
**Owner**: Repository and infrastructure maintainers
**Audience**: TokenMarket developers, API/Billing service maintainers, and workflow test adapters

## Public invocation

The root Makefile remains the only public entry:

```text
make dev [mode=local]
make dev-down [mode=local]
```

Omitted mode and explicit command-line `mode=local` are accepted. Any other value or origin that attempts to select test/prod fails with `INVALID_MODE` before `.env.local`, Docker configuration, DNS, sockets, images, or resources are accessed. `.env.local` must contain `MODE=local`, but it never selects or elevates effective mode.

Success is exit status 0; any failure is non-zero. Exact non-zero values are not stable. `make dev` and `make dev-down` replace the SF01 `SF02_NOT_READY` transition only; their names and root-entry status do not change.

This success/side-effect change activates Root Make Workflow v2 and is therefore breaking, even though the target names stay stable. The contract-first deprecation and consumer migration gate is defined in [`make-workflow-v2.md`](./make-workflow-v2.md). Pure action/mode validation and the documented read-only preflight precede lock-file creation. Once preflight succeeds, lock contention takes precedence over in-lock revalidation and mutation diagnostics.

## Required dependency set

Exactly three services are managed:

| Dependency | Container DNS | Host URL source | Default host endpoint | Container port | Persistence |
|------------|---------------|-----------------|-----------------------|----------------|-------------|
| PostgreSQL 15 | `postgres` | `DATABASE_URL` | `127.0.0.1:5432` | 5432 | Project named volume; durable local fact |
| Redis 7 | `redis` | `REDIS_URL` | `127.0.0.1:6379` | 6379 | Project named volume; preserved but rebuildable |
| Grafana OSS | `grafana` | `GRAFANA_URL` | `127.0.0.1:3000` | 3000 | Explicit `/var/lib/grafana` tmpfs; no anonymous/named volume |

Kafka/Redpanda, Prometheus, Loki, MinIO, frontend, gateway, and Python services are not started and cannot affect lifecycle success.

Definitions come from the runtime manifest validated by [`local-dependency-manifest.schema.json`](./local-dependency-manifest.schema.json). An exact official image tag without its reviewed multi-platform OCI index digest is invalid.

## Configuration contract

`make dev` reads exactly one ignored file: repository-root `.env.local`. Shell/environment values do not override lifecycle fields.

```text
MODE=local
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:<port>/<database>
REDIS_URL=redis://default:<password>@127.0.0.1:<port>/<db-number>
GRAFANA_URL=http://127.0.0.1:<port>
GRAFANA_ADMIN_PASSWORD=<synthetic-local-secret>
```

Rules:

- Every decoded local secret matches `^tm_local_[A-Za-z0-9_-]{32,96}$`. Percent encoding is accepted only when it decodes to that grammar. Whitespace, quotes, backslashes, delimiters, control characters, CR/LF and NUL are rejected, so Redis configuration generation cannot add a directive.
- Only the IPv4 literal `127.0.0.1` is accepted in SF02. No wildcard, hostname, LAN, production, test, IPv6, or remote address is accepted.
- PostgreSQL user/password/database and Redis default-user password/database number are required.
- Grafana URL contains no user-info; its administrator password is the separate field. Administrator username is the committed non-secret constant `admin`.
- URL query strings/fragments are rejected; Grafana path is empty or `/` only.
- Ports are 1–65535 and pairwise distinct. A host-port override is made only by changing its URL.
- `.env.example` values are unusable placeholders. Empty values, values outside the deterministic `tm_local_` grammar, provider-key-like values and non-local addresses fail closed; the workflow does not claim it can recognize every real-world production secret.
- Validation messages contain field names and recovery direction, not supplied values.

The workflow derives container URLs in memory by replacing host/port with the canonical service name/container port. It may derive dedicated child variables and fixed container secret-file targets, but these are not user configuration and cannot override the URL source.

`make dev-down` does not require, parse, or validate `.env.local`.

## Workspace identity and ownership

```text
canonical_path = NFC(physical_resolved_repository_root_without_trailing_separator)
workspace_hash = first_12_lower_hex(SHA256(UTF8(canonical_path)))
workspace_fingerprint = all_64_lower_hex(SHA256(UTF8(canonical_path)))
project_id     = "tokenmarket-" + workspace_hash
```

The canonical path is never emitted or stored in resource metadata. Branch name and configuration secrets are not inputs.

Every Compose command explicitly supplies the project ID and a secure `0700` project directory below the per-user runtime base. That directory is derived only from `project_id`; it is not the repository root. The adapter verifies that `infra/docker/compose.local.yml` is a regular non-symlink file whose bytes equal the committed Git blob, then supplies those bytes through stdin with `-f -`. The repository path therefore appears in neither Compose arguments nor Compose's canonical working-directory/config-file labels. A dirty or replaced Compose asset fails closed before Compose access. Compose project scope owns containers, default network, and named volumes. Resources carry:

```text
com.tokenmarket.repository=tokenmarket
com.tokenmarket.workspace-id=<project_id>
com.tokenmarket.workspace-fingerprint=<workspace_fingerprint>
```

Exact project ID plus the full fingerprint is the mutation boundary. A matching 12-hex project ID with a different full fingerprint is a detected hash collision and fails `RESOURCE_OWNERSHIP_CONFLICT` before mutation. Prefix/label discovery must report a different old workspace ID with recovery direction, but never adopt, stop, remove, rename, or attach its resources. Workspace movement creates a new project ID by design.

## Runtime and platform preflight

Supported hosts:

- macOS arm64 with local Docker Desktop Linux containers
- Linux x86_64 with a local Docker Engine

The reviewed toolchain is Docker 29.5.3 and Compose 5.1.4. Before configuration-dependent resource access, the workflow verifies:

1. Docker CLI and Compose exist and match the maintained versions.
2. The daemon is reachable and runs Linux containers on the expected architecture.
3. Required Compose options/JSON outputs exist; the maintained-version contract fixture has already proven environment-source secret `uid`/`gid`/`mode` semantics, so per-run preflight does not create a probe container.
4. The active endpoint is a local Unix socket. `tcp://`, `ssh://`, remote context, and remote `DOCKER_HOST` are rejected.

The workflow never installs/upgrades Docker, changes socket permissions/groups, invokes `sudo`, or changes daemon configuration.

## Lock contract

One non-blocking exclusive POSIX advisory file lock exists per project ID. On macOS the base is the OS-provided per-user temporary directory; on Linux it is an owned `/run/user/<euid>` directory when valid, otherwise an owned `0700` child below a root-owned sticky `/tmp`. Below it, a current-user `0700` directory named only from `project_id` contains the lock and an empty Compose project directory. Every path component is checked with no symlink following; the lock file is a regular current-user-owned `0600` file opened with `O_NOFOLLOW|O_CREAT`. Ownership, mode or type drift fails closed. No secret or raw workspace path is stored there.

For `dev`, pure action/mode, manifest/runtime, `.env.local`, read-only project inspection and no-credential port preflight occur before lock-file creation so an invalid request cannot modify even coordination metadata. The project lock is then acquired immediately before the first mutable action; runtime endpoint, ownership and port state are revalidated inside the lock to close the preflight race. It remains held across image pull, reconciliation, readiness, final state and final event emission. `dev-down` has no secret/config preflight and acquires the lock immediately after identity.

If the lock is held:

- the second operation emits `OPERATION_IN_PROGRESS`;
- it returns non-zero immediately;
- it creates, starts, stops, probes, or deletes nothing;
- the caller may retry after the active operation ends.

The kernel releases the lock on normal or abnormal process exit. Lock-file presence alone does not mean an operation is active.

## `make dev` ordered contract

1. Validate action syntax and effective local mode without reading `.env.local`, Docker, sockets or lock state.
2. Calculate identity; validate manifest, Docker/Compose/local endpoint, supported host and runtime capabilities read-only.
3. Read and validate `.env.local`; derive three secret payloads only in workflow memory.
4. Inspect exact-project identity/fingerprint/state/publishers read-only and perform the no-credential port preflight.
5. Acquire the secure project lock, create/verify its sibling safe Compose project directory, then revalidate local endpoint, ownership/state and ports. Any drift fails before pull or project mutation.
6. For each desired port after revalidation:
   - accept an exact-project publisher that matches service, bind address, and port;
   - otherwise test local bind availability without sending protocol data;
   - fail `PORT_CONFLICT` before creation if unavailable.
7. Pull only missing committed image digests. Emit pull result and duration per dependency.
8. Verify every image digest and native target-platform manifest locally.
9. Start one fresh monotonic 60-second readiness deadline.
10. Reconcile with the verified committed Compose bytes over stdin using `-f -`, the safe runtime project directory, and `up --detach --pull never`; Compose execution consumes the same deadline and is terminated/classified if no time remains.
11. Poll current per-service JSON state and run the three dependency-specific authenticated probes concurrently. Each attempt is bounded by the current remaining time; retries stop at the shared deadline. Compose healthchecks use the same authenticated semantics as supplementary evidence, but never extend or replace the workflow deadline.
12. Emit per-dependency final results and aggregate success only when all three have fresh evidence before that deadline. No post-deadline probe can turn the run into success.

Healthy repeat-start adds no container, network, or volume and must finish within 15 seconds. It does not contact the registry or rewrite configuration/locks.

Failure after resource creation preserves inspectable project state and all volumes. The workflow does not automatically down, roll back, delete volumes, migrate, seed, or reset. Normal exact-owned reconciliation may replace a container whose image differs from the verified desired digest, but it preserves its declared named volume. Fixing the reported cause and rerunning must reconcile safely.

## Readiness contract

| Dependency | Liveness evidence | Final readiness evidence |
|------------|-------------------|--------------------------|
| PostgreSQL | Container process plus TCP server status | Configured user/password/database authenticates over TCP and `SELECT 1` returns exactly `1` |
| Redis | Container process responds at protocol level | Default user authenticates with the URL password and same connection returns `PONG` to `PING` |
| Grafana | `GET /api/health` returns 200 | Health JSON has `database=ok`; Basic Auth `GET /api/user` returns 200 and `isGrafanaAdmin=true` |

Container `running`, open TCP port, `pg_isready`, unauthenticated Redis reachability, Grafana homepage, or stale health is insufficient by itself. The reconcile call, state polling and concurrently scheduled probes share the same overall 60-second readiness deadline. Only safe categories, not raw probe output, are emitted.

## Secret transport and output

- Parsed secrets exist in a dedicated child-process environment mapping only for the Compose invocation; the mapping is never merged into the parent environment, printed, returned in exceptions or retained after the call.
- Compose top-level secrets use `environment` sources and per-service long syntax. The reviewed manifest supplies each verified non-root runtime UID/GID and mode `0400`; unlike file-source secrets, this transport applies ownership/mode inside the container and avoids a host bind-permission mismatch.
- PostgreSQL uses `POSTGRES_PASSWORD_FILE` through its mounted secret.
- Redis starts from a mounted `0400` secret `redis.conf` containing exactly one `requirepass tm_local_...` directive; password is not a process argument and the strict grammar makes quoting/config injection impossible.
- Grafana uses `GF_SECURITY_ADMIN_PASSWORD__FILE`.
- Redis client probes use a short-lived `REDISCLI_AUTH` subprocess environment, never `redis-cli -a`.
- Compose config output, inspect health output, HTTP bodies, URLs with user-info, child environment mappings, and command exceptions are internal only and always redacted before categorization.
- Every JSONL record is a standard event envelope with a unique UUID `event_id`, stable `event_type=workflow.step`, `schema_version=2.0.0`, UTC RFC 3339 `timestamp`, `producer=repository-workflow`, and a lifecycle-run `correlation_id`. Its strict `payload` contains action, component, phase, status, code, duration and safe message; dependency-scoped phases include `dependency`, while aggregate identity/final payloads may omit it.
- Plain text records express the same safe payload semantics and correlation ID. Neither form relies on color, icons, animation, or interactive terminal behavior.

## `make dev-down` ordered contract

1. Validate action/mode, then calculate identity and acquire the same project lock without reading configuration.
2. Validate only the local runtime facts needed to address the exact project.
3. Discover exact-project resources and scan repository labels for moved-workspace resources. Different workspace IDs are mandatory report-only findings with recovery direction.
4. If no exact-project container or network exists (preserved named volumes may remain), return success (`already stopped`). Stopped containers or an orphan network still require reconciliation.
5. Execute exact-project `down --remove-orphans` from the same verified committed Compose bytes over stdin, safe runtime project directory, and safe `tm_local_` parse-only secret values, without a CLI timeout override, `--volumes`, `--rmi`, or prune. Compose therefore uses the declared per-service grace: PostgreSQL 60 seconds and Redis/Grafana 30 seconds. The workflow subprocess/state-verification deadline is 75 seconds.
6. Confirm exact-project containers and temporary network are absent; confirm named volumes remain.
7. Discard the parse-only child environment and release the lock after final events.

If Compose cannot parse for down, a fallback may stop/remove only containers and networks whose Compose project label exactly equals the computed project ID and full fingerprint. It never touches volumes or prefix-matched resources. A stop timeout/forced termination is failure evidence, not silent success.

## Data semantics

- PostgreSQL named volume is retained across down/up, retries, partial failures, command interruption, and host restart.
- Redis named volume is also retained by ordinary down, but Redis content is never a durable fact and all behavior must recover from it being empty.
- Grafana `/var/lib/grafana` is explicit 0700 tmpfs owned by its verified runtime UID/GID, so the image can write without root and cannot create an anonymous data volume. State is ephemeral in SF02; data sources, dashboards, and alerts are owned by SF19.
- Start/down never runs Alembic, initializes business schema, seeds data, rotates an existing PostgreSQL role password, or copies production data.
- SF02 exposes no destructive cleanup target. A future cleanup action needs a separate contract, impact statement, and strong confirmation.

## Stable diagnostics

| Code | Meaning | Side-effect boundary/recovery |
|------|---------|-------------------------------|
| `INVALID_MODE` | Non-local or unsafe mode origin | Before configuration/resource access; retry local |
| `INVALID_CONFIG` | Missing/invalid/placeholder/non-local field | Before creation; fix named field |
| `TOOL_MISSING` | Docker or Compose absent | Before resource change; install reviewed tool externally |
| `TOOL_VERSION_UNSUPPORTED` | Runtime/version/platform/capability unsupported | Before resource change; use maintained runtime |
| `IMAGE_UNAVAILABLE` | Pull, digest, platform, disk, or identity verification failed | Before container creation; fix registry/disk/manifest |
| `PORT_CONFLICT` | Desired loopback port is owned elsewhere or lost to bind race | Never stop owner; free port/change URL and retry |
| `DEPENDENCY_NOT_READY` | Authenticated readiness failed or timed out | Project state retained; inspect safe diagnostics/fix/retry |
| `OPERATION_IN_PROGRESS` | Per-project lock held | No side effects; retry later |
| `RESOURCE_OWNERSHIP_CONFLICT` | Exact name/project resources do not match owned identity | No adoption/deletion; follow recovery guide |
| `STEP_FAILED` | Unexpected bounded Compose/stop failure | State retained; inspect and retry |

`SF02_NOT_READY` remains reserved as historical SF01 transition evidence but is no longer emitted by implemented `dev`/`dev-down`.

All diagnostics are detected synchronously by the local CLI and are **local blocking / no automated page** severity: no shared production service is being monitored, so paging would be misleading. Repository workflow maintainers own mode/lock/event failures; infrastructure maintainers own Docker/image/port/resource/Compose failures; API/Billing owners own their service readiness failures. Every code links to `ops/runbooks/local-environment.md`; an implementation without that owner/recovery mapping fails contract checks.

## API/Billing consumer contract

SF02 does not start business services. When API Service or Billing Service is started independently:

- `/health/live` never probes PostgreSQL and remains available while PostgreSQL is down.
- `/health/ready` executes an independently owned, two-second bounded async `SELECT 1` probe.
- Ready returns the existing 200 response shape.
- Invalid configuration, connection, authentication, timeout, or query failure returns the 503 shape from [`service-health-v1.1.openapi.yaml`](./service-health-v1.1.openapi.yaml).
- Probe failure is evaluated fresh; recovery can return to 200 without restarting the service.
- Gateway, Admin Service, Redis, Kafka, and providers are not added as readiness dependencies in SF02.

## Compatibility and change control

- Public target renames/removal, volume deletion on ordinary down, a larger dependency set, non-local modes, remote Docker contexts, or non-loopback publishing are breaking changes.
- Host URL grammar, canonical service names, project-hash rule, image identity, readiness probes, persistence class, event fields/codes, and stop semantics are reviewed contracts.
- Root target semantics and event changes follow [`make-workflow-v2.md`](./make-workflow-v2.md) and [`workflow-event-v2.0.schema.json`](./workflow-event-v2.0.schema.json). Health changes follow the OpenAPI contract.
- A dependency release/digest change updates the runtime manifest, scan/license evidence, ADR reference, both platform validations, and rollback identity together.
