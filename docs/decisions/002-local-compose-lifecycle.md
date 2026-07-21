# ADR 002: Local Dependency Lifecycle via Docker Compose

**Status**: Accepted
**Implementation Verification**: Pending — requires both-platform lifecycle, security, persistence, recovery, accessibility, and performance evidence before public v2 activation
**Date**: 2026-07-15
**Owner**: TokenMarket Engineering
**Deciders**: Repository maintainers / Platform team

## Context

SF02 must replace the SF01 `SF02_NOT_READY` transition with a reproducible local lifecycle for PostgreSQL 15, Redis 7, and Grafana. The same public commands must work on macOS arm64 and Linux x86_64, isolate multiple clones/worktrees, preserve PostgreSQL data, reject non-local configuration, serialize concurrent operations, and expose authenticated readiness without leaking synthetic local credentials.

The repository already owns a Python workflow tool, a root Make contract, structured workflow events, configuration redaction, and Docker as a maintained toolchain. Introducing a separate orchestration CLI would duplicate these controls.

## Decision

Use one committed Docker Compose application at `infra/docker/compose.local.yml`, invoked only through the existing Python workflow tool and the root targets `make dev` and `make dev-down`.

The adapter will:

1. Derive `tokenmarket-<12-hex-sha256>` from the canonical workspace root, label resources with the full 64-hex fingerprint, fail closed on a short-hash collision, and pass the short ID explicitly as the Compose project name. Verify the committed Compose blob, pipe its bytes through `-f -`, and use a `0700` project directory derived only from the project ID so Compose canonical labels never retain the raw workspace path.
2. Use project-scoped containers, network, and named volumes; never set fixed `container_name` or global volume names.
3. Consume a versioned local-dependency manifest containing exact image tags, multi-platform OCI index digests and both target-platform child digests for PostgreSQL, Redis, and Grafana.
4. Pull only missing declared digests, then start one 60-second readiness deadline covering Compose reconcile, state collection and concurrent authenticated probes with no further pull.
5. Bind published ports only to `127.0.0.1`; derive their values and all container addresses from the three validated host URLs.
6. Require injectable-safe `tm_local_` credentials, pass them only to a dedicated Compose child mapping, and use environment-source secrets to create 0400 files owned by each verified upstream non-root UID/GID; redact all subprocess/event failures.
7. Serialize the complete lifecycle with a per-project non-blocking POSIX advisory lock.
8. Preserve PostgreSQL and Redis named volumes on ordinary down; mount Grafana `/var/lib/grafana` as tmpfs so ephemeral state creates no anonymous volume until SF19 owns dashboards and data sources.
9. Publish Root Make/workflow event v2 as a standard event envelope with unique event ID, stable type, schema version, UTC timestamp, producer, lifecycle correlation ID and strict workflow-step payload, with an explicit consumer migration/deprecation gate rather than mutating strict v1 contracts; translate Compose JSON and authenticated probes instead of exposing Docker output as an API.
10. Reject remote Docker endpoints because host locks and port ownership checks cannot protect a remote daemon.

Selected dependency releases are PostgreSQL `15.18-bookworm`, Redis `7.2.14-bookworm`, and Grafana OSS `13.0.3`; the implementation change must resolve, verify, scan, and commit real multi-platform index and both target child digests before the Compose asset is accepted.

### Resolved dependency evidence (verified 2026-07-16)

Method: each OCI index digest was computed as the SHA-256 of the raw index document fetched through two independent registry mirrors and cross-checked equal; child digests were read from the index manifest lists; linux/arm64 images were pulled and executed natively on darwin/arm64 with Docker 29.5.3 and Compose v5.1.4. Canonical machine-readable values are committed in `ops/workflow/local-dependencies.json`.

- **PostgreSQL `15.18-bookworm`** (`docker.io/library/postgres`): index `sha256:b0c5bab0fbba8e0c221f73b1dc6359ec35f8650074377e727299df248fc8ad51`; linux/amd64 `sha256:fafb7480959eeeb7f1e43b479e642ffef2aa0f067242a1954ab41f2d764e2786`; linux/arm64 `sha256:92c67be3a884bc55d99e73dab0baca3f7a2c1591dc1828abadfdd640b10866c8`; runtime `uid=999 gid=999` (`postgres`); PostgreSQL License.
- **Redis `7.2.14-bookworm`** (`docker.io/library/redis`): index `sha256:f0707c78ea880b293ccdeb410c9c0a8ccae93fe7128799b751333a698b0a39a7`; linux/amd64 `sha256:86778a4a011a500d9a502858e27647380b62e5e8fbadef3f59e506f0899792fd`; linux/arm64 `sha256:7ee8f94475527b5d6a1077c2be9d7fab2b1417fe0d9985ffd28f29764c79c291`; runtime `uid=999 gid=999` (`redis`); BSD 3-Clause (final BSD-licensed Redis release line).
- **Grafana OSS `13.0.3`** (`docker.io/grafana/grafana`): index `sha256:1a345428a36270f5fb9add69fea71450a5843c15266c99359d6d380470ab19c9`; linux/amd64 `sha256:65f8af7bd56f4010036ca45ef301deae30bd102880926bfd48f8c19be85b6fd8`; linux/arm64 `sha256:d2ee7728138ac45709a1dde82eebadd85f9768eb46b528665f78426c606a35b5`; AGPL-3.0, used unmodified as a local container with no distribution or hosted-service offering. Upstream runs as `uid=472` with primary group `0` (root); the frozen manifest schema requires `runtime_gid >= 1` and the data model requires a verified non-root runtime identity, so the Compose asset pins `user: "472:472"` and a `/var/lib/grafana` tmpfs with `uid=472,gid=472,mode=0700`. Verified on Docker 29.5.3 that Grafana 13.0.3 starts as `472:472` on that tmpfs and `GET /api/health` returns 200 with `database="ok"`; the manifest records `runtime_uid=472, runtime_gid=472`.

Vulnerability scans (Trivy, severities HIGH/CRITICAL, against the pinned digests, 2026-07-16; scans are reproducible from the committed digests and are re-run on any dependency change):

- PostgreSQL: 16 CRITICAL / 45 HIGH findings — 7 unique CVEs, all in Debian bookworm userland (`perl` 5.36 CVE-2026-13221/42496/8376, `zlib1g` CVE-2023-45853, `libsqlite3-0` CVE-2025-7458, `libxml2` CVE-2026-6653) plus one Go `stdlib` CVE-2025-68121 in a bundled Go tool; none in the PostgreSQL server build itself.
- Redis: 4 CRITICAL / 17 HIGH — `perl-base` CVE-2026-13221/42496/8376 and `zlib1g` CVE-2023-45853 from the bookworm base.
- Grafana: 0 CRITICAL / 32 HIGH.

Risk acceptance: containers bind loopback only, run non-root with 0400 synthetic local credentials, and hold no production data, so bookworm userland exposure is accepted for local development. Resolution and scan evidence are re-produced whenever a tag or digest changes, per the rollback and dependency-change rules below.

## Ownership

- **Public command and event owner**: Repository workflow maintainers.
- **Compose and dependency-manifest owner**: Infrastructure maintainers.
- **API/Billing readiness owner**: Each service owner; implementations and secret-free Prometheus probe metrics remain independent.
- **PostgreSQL local data owner**: Developer/workspace identified by the project hash.
- **Security review**: Required for image, digest, license, bind, secret-transport, or remote-context changes.

## Options considered

### Rootless/native host services

Rejected. Package managers and service managers differ across supported platforms, versions are harder to isolate, and the workflow would need system installation/upgrade authority that SF02 explicitly forbids.

### Docker SDK orchestration without Compose

Rejected. It would recreate Compose's declarative network, volume, health, reconciliation, and down behavior while adding an SDK dependency and a larger API compatibility surface.

### Makefile or shell-only Compose wrapper

Rejected. Cross-process locks, strict URL parsing, JSON state translation, redaction, and deterministic negative tests fit the maintained Python workflow tool better and would otherwise be duplicated.

### Separate Compose definitions per platform/workspace

Rejected. Multi-platform index images, named volumes, and published ports already provide a common definition; overrides would introduce divergent contracts.

## Failure modes and controls

| Failure mode | Required behavior | Recovery |
|--------------|-------------------|----------|
| Docker/Compose missing, daemon unavailable, remote endpoint, unsupported platform | Fail before configuration-dependent resource changes with a stable tool/runtime diagnostic | Start or install the reviewed local runtime; rerun the same command |
| Missing image | Pull only the committed digest and report pull separately | Fix registry/network/disk; rerun without deleting resources |
| Digest/platform mismatch | Fail before creating containers | Review and replace the manifest digest in a dependency-change PR |
| Port owned by another process/project | Fail before project creation; never probe with credentials or stop the owner | Free the port or change the corresponding URL, then rerun |
| Dependency alive but authentication/query fails | Return dependency-not-ready inside the shared deadline, preserve inspectable resources, redact raw output | Fix local synthetic credentials/config; rerun |
| Concurrent up/down | One holder proceeds; loser fails immediately with no side effects | Retry after the active operation ends |
| 12-hex project collision/full fingerprint mismatch | Fail before mutation and report ownership conflict | Use the documented explicit recovery; never adopt the other workspace |
| Process/host interruption | Kernel releases lock; project resources and volumes remain reconcilable | Rerun `make dev` or `make dev-down` |
| Missing/corrupt `.env.local` during down | Compute project id/fingerprint without secrets and parse Compose with safe child-environment placeholders | Rerun down; use exact-project/fingerprint fallback only if Compose parsing fails |
| Stop exceeds service grace or 75-second outer bound, or requires forced kill | Report failure; never delete volumes | Inspect safe logs/state, repair runtime, retry down |
| Any non-current image on an exact-owned container | Verify desired index/child digests, replace the container, preserve its declared named volume | Retry or roll back the desired dependency set; image mismatch alone is not an ownership conflict |
| Workspace moved | New identity is created; old labeled resources are reported but not adopted | Return to old path or follow an explicit reviewed recovery procedure |

## Security and data consequences

- Local credentials use a deterministic synthetic grammar, stay in ignored `.env.local` plus a short-lived Compose child mapping, become only 0400 UID/GID-owned container secret files, and are never suitable for production.
- `127.0.0.1` publishing and a project network reduce exposure but do not make the environment suitable for untrusted networks.
- PostgreSQL is the only durable local fact source. Ordinary lifecycle operations never run migrations, seed data, alter roles, or delete volumes.
- Redis content is rebuildable even though its named volume is preserved by ordinary down.
- Grafana `/var/lib/grafana` is tmpfs and creates no anonymous volume in SF02; SF19 must record a new decision if it introduces durable dashboards, data sources, or password-rotation semantics.

## Rollout

1. Accept this ADR as the implementation-authorizing design decision, then merge Root Make/event v2 contracts, migration notice, manifest schema, and failing tests while v1 `SF02_NOT_READY` remains active and implementation verification remains Pending.
2. Resolve and scan official multi-platform digests; commit the runtime manifest and Compose asset.
3. Implement the guarded workflow activation candidate and migrate all enumerated event consumers to the v2 standard envelope without replacing the public SF01 transition yet.
4. Add API/Billing PostgreSQL readiness and safe probe metrics after the shared health contract is updated.
5. Run accessibility and dirty-worktree gates plus isolated Linux x86_64 and representative macOS arm64 lifecycle/security/persistence/recovery/performance evidence.
6. Only after all evidence passes, atomically replace the SF01 dev/dev-down transition, event output, help and recovery documentation, then mark Implementation Verification as Verified without changing the already-Accepted design status.

## Rollback

- Revert the workflow adapter, Compose asset, manifest, event v2 activation/health update, and service readiness changes together in a reviewed PR; restore v1 runtime output while retaining immutable v2 migration history.
- Restore the SF01 fail-closed `SF02_NOT_READY` adapter if lifecycle safety cannot be established; do not emulate success.
- Never use rollback to delete project volumes. Existing project-scoped PostgreSQL/Redis volumes remain for a later compatible forward fix or explicit manual recovery.
- Image rollback changes tag, OCI index digest and both child digests together, with both target-platform manifests and scan evidence revalidated.

## Consequences

### Positive

- One public workflow and one Compose definition cover both supported platforms and multiple worktrees.
- Immutable images, authenticated probes, bounded waits, locks, and project scoping make repeated lifecycle operations diagnosable and recoverable.
- One reviewed asyncpg 0.30.x dependency is added to the independent workflow lock for the PostgreSQL host query; no Docker SDK or second orchestration CLI is introduced.

### Negative

- Docker/Compose version and local-daemon availability become hard prerequisites.
- Compose environment-source secret support and pinned image runtime UID/GID are hard compatibility requirements and need explicit cross-platform tests.
- Grafana local state is intentionally reset across ordinary down/up; durable monitoring configuration waits for SF19.
- A moved workspace does not automatically adopt old volumes, by design.

## References

- `specs/002-local-dependency-lifecycle/spec.md`
- `specs/002-local-dependency-lifecycle/research.md`
- `specs/001-repository-workflow-baseline/contracts/make-workflow.md`
- `specs/001-repository-workflow-baseline/contracts/workflow-event.schema.json`
- `specs/001-repository-workflow-baseline/contracts/environment-mode.md`
- `.specify/memory/constitution.md`
