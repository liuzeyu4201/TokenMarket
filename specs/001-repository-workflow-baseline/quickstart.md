# Quickstart Validation: 仓库工程工作流基线

**Feature**: `001-repository-workflow-baseline`

**Purpose**: Runnable acceptance guide after implementation; it does not replace automated tests

**Safety**: Do not use real credentials or production configuration

## 1. Prerequisites

Use a fresh checkout or a disposable working copy. Required versions and integrity references are owned by the repository toolchain files; verify rather than relying on whatever is preinstalled.

```bash
make help
make toolchain-check
make bootstrap
```

Expected:

- `make help` completes in under 2 seconds and lists `dev`, `dev-down`, `fmt`, `lint`, `test`, `build`, `migrate` with prerequisites, side effects and recovery.
- `toolchain-check` reports the supported Make, Go, Python/uv, Node/npm, Docker and scanner versions without installing or upgrading them.
- `bootstrap` prepares only lock-resolved repository-tool, Go, Python-service and frontend dependencies; it does not install system tools or rewrite any lockfile, and a second run resolves the same dependency graph.
- Missing or unsupported tools fail within 5 seconds before any persistent side effect.

See [`contracts/make-workflow.md`](./contracts/make-workflow.md) for the command contract.

## 2. Prepare synthetic local configuration

```bash
cp .env.example .env.local
git status --short
```

Expected:

- `.env.local` is ignored and does not appear in status.
- `.env.example` contains names, comments and unusable placeholders only.
- No command prints configuration values.

Do not replace placeholders with provider keys or production values for SF01 validation.

## 3. Validate successful root and supporting actions

```bash
make fmt
make fmt-check
make type-check
make lint
make test
make build
```

Expected:

- All eight required components run real adapters; none is silently skipped.
- Go gateway, three Python services and frontend each execute a real smoke test.
- `shared`, `infra` and `ops` each execute negative fixture tests and create a deterministic asset archive.
- Five immutable service images build with version/SHA tags; no `latest` tag is created.
- A second `make fmt` produces no new differences.
- Required component with zero discovered tests or an empty action adapter makes the aggregate fail.

Automated tests cover injected component failures; do not delete a real component to test this manually.

## 4. Validate dirty-worktree formatting safety

Run the repository workflow test dedicated to dirty worktrees through the public test target:

```bash
make test
```

The fixture creates a disposable repository copy containing tracked edits, an out-of-scope file and an untracked file. It proves that `make fmt`:

- formats only declared files;
- never runs reset, checkout, stash, clean or delete;
- preserves out-of-scope and untracked content;
- produces zero additional differences on the second run.

The canonical behavior is defined in [`contracts/make-workflow.md`](./contracts/make-workflow.md).

## 5. Validate SF02 transition behavior

Before SF02 is implemented, run each target separately and expect a non-zero result:

```bash
make dev
make dev-down
```

Expected for both:

- Diagnostic code is `SF02_NOT_READY`.
- Output states that SF02 must provide the lifecycle adapter.
- Docker is not inspected or invoked.
- No configuration file is read.
- No container, volume, network or worktree file is created, stopped, removed or changed.

This expected failure is a passing SF01 acceptance condition. After SF02, this section is superseded by SF02's lifecycle quickstart while the public target names remain unchanged.

## 6. Validate environment-mode safety

The grammar and approval rules are in [`contracts/environment-mode.md`](./contracts/environment-mode.md).

### Invalid mode

```bash
make migrate mode=PROD
```

Expected: non-zero `INVALID_MODE` before any configuration, DNS or network access.

### Omitted mode

```bash
make migrate
```

Expected: effective mode is `local`. If no local database is externally available, the command fails safely with the missing local configuration/dependency name; it never starts a database or falls through to test/production.

### Shell-origin escalation

```bash
mode=prod make migrate
```

Expected: shell origin cannot select production; the action stays local or fails safe if origin is ambiguous.

### Production without approval

```bash
make migrate mode=prod
```

Expected: `PROD_APPROVAL_REQUIRED` before production configuration or resource access. This guide intentionally does not provide the production confirmation phrase or approval proof.

Never use an actual production URL to test these preflight cases.

## 7. Validate migration ownership and round-trip

```bash
make migrate-check
make migrate-integration-check
```

Expected:

- Owners are exactly `api-service` then `billing-service`; `admin-service` is explicitly a non-owner.
- Each initialized migration graph has one head and valid upgrade/downgrade metadata.
- Zero pending revisions is reported explicitly only after graph and owner validation.
- The command performs no network operation.

`migrate-integration-check` is the separate integration layer: it starts only a fixed-digest PostgreSQL 15 container with synthetic credentials, runs API then Billing forward migration, backout, retry and final-head restoration, then discards the fixture. It never calls `make dev` or contacts a shared database.

`make ci` must invoke both migration checks and cannot replace the integration layer with YAML or offline validation.

## 8. Validate path and terminal accessibility

```bash
NO_COLOR=1 make help
make test
```

Expected:

- Plain-text status remains complete without color or icons.
- Workflow fixture tests run the repository from a disposable path containing both spaces and Chinese characters.
- Paths in events are repository-relative and no same-named directory outside the fixture is accessed.
- JSON Lines events validate against [`contracts/workflow-event.schema.json`](./contracts/workflow-event.schema.json).

## 9. Validate security gates

```bash
make security-check
```

Expected:

- Full-history secret scan passes for the repository and detects the synthetic positive fixture.
- Go, all Python locks and the npm lock are scanned without modifying lockfiles.
- Scanner/database download failure remains a failed gate after at most one bounded retry.
- Output redacts fixture values.

After `make build`:

```bash
make image-scan
```

Expected: all five immutable images are scanned for HIGH/CRITICAL findings; an exception is accepted only when it contains the required ID, analysis, owner, approval, issue and expiry.

## 10. Run the complete local CI gate

```bash
make ci
```

Expected:

- The sequence matches [`contracts/ci-gates.md`](./contracts/ci-gates.md).
- The final event is `PASSED` only when every blocking step produces evidence.
- Re-running on the same commit produces the same result and no unexpected tracked differences.
- No service is published or deployed.

## 11. Verify hosted CI

Open or update a pull request against `main` after implementation.

Expected:

- Exactly one stable required check, `quality-gate`, runs without path filtering.
- The workflow invokes `make ci` as its only project command.
- A deliberately failing fixture in a disposable test branch blocks the merge.
- A successful merge triggers the same gate for the final `main` commit.
- Workflow token permissions are read-only and no repository/production secret is available.

## 12. Evidence to attach to review

- `make help` and `toolchain-check` output.
- Component test counts and coverage summaries.
- Contract, boundary and migration-check results.
- Five immutable image references plus runtime health smoke results.
- Secret/dependency/image scan summaries with sensitive values redacted.
- `quality-gate` URL/result for PR and final main commit.
- Confirmation that no business schema, provider credential, production resource or deployment was introduced.
