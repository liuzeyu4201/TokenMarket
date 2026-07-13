# Contract: Root Make Workflow

**Version**: 1.0.0

**Owner**: Repository maintainers

**Audience**: Developers, CI adapters and future component maintainers

## Invocation

All public actions are invoked from any working directory through the repository-root Makefile. Documentation examples use the repository root:

```text
make <target> [mode=local|test|prod]
```

The workflow resolves paths from its own location. Repository paths containing spaces or non-ASCII characters are supported. Public success semantics are `0 = success`; any non-zero result is failure. Exact non-zero numbers are not stable API because Make may normalize child process exit values.

## Public targets

| Target | Purpose | Side effects | Success evidence | Required failure behavior |
|--------|---------|--------------|------------------|---------------------------|
| `help` | Show commands, prerequisites, side effects and recovery | None | All public and stable supporting targets documented; completes within 2 seconds | Help itself must not run preflight or mutate state |
| `dev` | Start local dependencies after SF02 | Local resources after SF02 | SF01: never succeeds; SF02 will define health evidence | Before SF02, emit `SF02_NOT_READY`, perform no Docker/config/network action, return non-zero |
| `dev-down` | Stop local dependencies after SF02 without deleting durable data | Local resources after SF02 | SF01: never succeeds; SF02 will define stop evidence | Same SF01 blocked behavior as `dev`; future normal stop cannot delete volumes |
| `fmt` | Apply repository formatters | Declared source/config files | Every required component ran a real formatter; second run adds no differences | Never reset, delete, stash, checkout or modify outside declared scope |
| `lint` | Static, type, boundary and contract validation | None except declared caches | Every required component produces a real report | Missing component, tool, adapter or required check fails the aggregate |
| `test` | Run all component and workflow tests | Ephemeral test resources/artifacts | Each required component reports at least one executed test | Zero tests, skipped required suite or component failure fails aggregate |
| `build` | Build five service images and three deterministic asset bundles | Build artifacts and local images | Immutable-tagged images and reproducible asset archives exist | Missing lockfile, cross-context copy, root image or non-reproducible asset fails |
| `migrate` | Apply reviewed owner migrations to selected external environment | Persistent database state | Owner order and applied/pending count reported | Validate mode/approval/config before connection; never start DB; partial failure non-zero with backout reference |

## Supporting targets

| Target | Contract |
|--------|----------|
| `bootstrap` | After `toolchain-check`, prepare only committed-lock-resolved project dependencies for workflow tooling and applicable components; never install system tools, rewrite locks or infer new versions; a second run is resolution-idempotent |
| `type-check` | Run the complete independently callable Go/Python/TypeScript type-check set; `lint` also aggregates this same set rather than defining a second implementation |
| `toolchain-check` | Validate tools, versions, lockfiles and integrity references before side effects |
| `fmt-check` | Non-modifying formatter check for daily use and CI preflight |
| `structure-check` | Reconcile component manifest, paths, owners, tests, adapters and allowed dependencies |
| `contracts-check` | Validate contract schemas, versions, ownership, links and generated drift |
| `migrate-check` | Offline graph/owner/backout validation; CI may add isolated PostgreSQL forward/backout evidence |
| `migrate-integration-check` | Start only a pinned isolated PostgreSQL 15 container with synthetic credentials, run API then Billing forward/backout/retry/final-head restoration, and discard the fixture; never call `dev` or contact a shared database |
| `security-check` | Secret and locked-dependency scans; fails closed on scanner/database failure |
| `image-scan` | Scan the immutable images produced by `build`; block HIGH/CRITICAL unless approved exception exists |
| `ci` | Execute the full required gate in a stable order; is the only project command in CI YAML |

## Aggregate execution

1. Resolve repository root without relying on caller `pwd`.
2. Validate action syntax and environment mode.
3. Run toolchain/configuration preflight before side effects.
4. Load the single component manifest.
5. Execute required component actions in manifest order and fail fast.
6. Emit safe step events and a final aggregate event.
7. Return `0` only if every required step produced its required evidence.

When a required step fails, remaining required steps are `SKIPPED` with the failure reason; they are never reported as passed. Re-running after fixing the cause must be safe.

## CI aggregate order

`make ci` performs:

1. `toolchain-check`
2. `bootstrap`
3. `fmt-check`
4. `type-check`
5. `lint` (including structure and contract checks and reusing the same type-check implementation)
6. `test`
7. `migrate-check`
8. `migrate-integration-check`
9. `security-check`
10. `build`
11. container health smoke
12. `image-scan`

The CI adapter may install verified tools and manage download caches, but may not duplicate component commands or turn a failure into a warning.

## Stable diagnostic codes

`INVALID_USAGE`, `TOOL_MISSING`, `TOOL_VERSION_UNSUPPORTED`, `INVALID_CONFIG`, `INVALID_MODE`, `PROD_APPROVAL_REQUIRED`, `SF02_NOT_READY`, `COMPONENT_NOT_INITIALIZED`, `NO_TESTS_EXECUTED`, `STEP_FAILED`, `CONTRACT_DRIFT`, `MIGRATION_INVALID`, `SECRET_DETECTED`.

Messages contain variable names, component IDs and repository-relative paths only. Values classified as secret, personal or financial must be redacted before serialization.

## Accessibility

- Plain text status and final outcome are always present.
- Color and icons are optional and cannot carry unique meaning.
- `NO_COLOR` and non-TTY output disable color.
- JSON Lines output follows [`workflow-event.schema.json`](./workflow-event.schema.json).

## Compatibility

Adding a supporting target is backward-compatible. Renaming/removing a public target, changing its side-effect class, allowing a previously rejected environment escalation, or changing success semantics is breaking and requires a new contract version plus a migration notice.
