# Data Model: 仓库工程工作流基线

**Feature**: `001-repository-workflow-baseline`

**Date**: 2026-07-13

**Persistence model**: Version-controlled engineering metadata plus ephemeral run evidence; no business database tables

## Overview

This feature models repository workflow facts rather than TokenMarket business data. Durable definitions live in version control and are validated against the schemas in [`contracts/`](./contracts/). Runtime command events and CI evidence are ephemeral outputs retained by the local terminal or CI platform.

```text
ComponentBoundary 1 ── * ComponentActionBinding * ── 1 WorkflowCommandDefinition
        │                              │
        ├── * ToolchainRequirement     └── * WorkflowStepResult
        └── * SharedContractArtifact             │
                                                  *
EnvironmentSelection 1 ── 0..1 ProductionApproval   WorkflowRun
        │
        └── 0..* MigrationPlan ── 1 MigrationOwner

CIGate * ── 1 WorkflowCommandDefinition
```

## Entity: WorkflowCommandDefinition

Represents one public or supporting root workflow action.

| Field | Type | Rules |
|-------|------|-------|
| `name` | string | Unique, lowercase kebab-case; public names are `help`, `dev`, `dev-down`, `fmt`, `lint`, `test`, `build`, `migrate`; stable supporting names include `bootstrap`, `type-check`, `migrate-integration-check` |
| `visibility` | enum | `public` or `supporting` |
| `purpose` | string | Non-empty, safe for help output |
| `preconditions` | list | Ordered checks that run before side effects |
| `ordered_steps` | list | References component actions or workflow checks |
| `side_effect_class` | enum | `none`, `workspace-format`, `local-resource`, `persistent-data`, `artifact-build` |
| `mode_policy` | enum | `not-applicable`, `optional-default-local`, `required` |
| `success_semantics` | string | Must define observable evidence, never only “command returned” |
| `failure_codes` | list | Values allowed by the workflow event contract |
| `recovery` | string | Safe retry/backout instructions |
| `output_contract_version` | string | Semantic version of workflow event schema |

**Invariants**:

- Every public command appears exactly once; stable `bootstrap` and `type-check` support commands also appear exactly once.
- `bootstrap` validates system tools first, uses committed locks, never installs system tools and never rewrites a lockfile.
- A command with side effects lists preconditions before the first side-effecting step.
- A required step cannot have an empty adapter or empty evidence rule.
- `dev` and `dev-down` remain public while their capability is `blocked_on_sf02`.
- Exact numeric non-zero exit codes are not part of the public contract.

**Owner/source of truth**: Repository maintainers; root Make workflow and command contract.

**Classification/retention**: Public engineering metadata; retained in Git history.

**Audit**: Semantic changes require spec/contract/CI updates in the same reviewed change.

## Entity: ComponentBoundary

Represents one required ownership boundary.

| Field | Type | Rules |
|-------|------|-------|
| `id` | enum | `proxy-gateway`, `api-service`, `billing-service`, `admin-service`, `frontend`, `shared`, `infra`, `ops` |
| `path` | repository-relative path | Unique; must resolve inside repository root |
| `owner` | string | Non-empty team or maintainer role |
| `responsibility` | string | Must not duplicate another component's domain ownership |
| `component_type` | enum | `go-service`, `python-service`, `web-frontend`, `contract-assets`, `infrastructure-assets`, `operations-assets` |
| `allowed_dependencies` | list of component IDs | Directional allowlist; self-reference forbidden |
| `test_root` | path | Must exist inside component path and contain discoverable tests |
| `deliverable_type` | enum/list | Binary, container image, static site image, deterministic asset archive |
| `required` | boolean | Always `true` for SF01's eight boundaries |
| `lifecycle_state` | enum | `declared`, `scaffolded`, `verified` |

**Invariants**:

- Path uniqueness is case-sensitive and symlink resolution may not escape repository root.
- A service cannot import another service's internal package or read its persistence store.
- `shared` stores versioned contracts and generated metadata, not copied service business logic.
- `admin-service` has no migration ownership in SF01 and cannot access API/billing storage.
- `verified` requires all mandatory action bindings to produce evidence.

**State transition**:

```text
declared ── structure created ──> scaffolded ── fmt/lint/test/build pass ──> verified
   ^                                  │
   └──── missing/invalid structure ───┴──── contract or action failure ───> failed run
```

**Owner/source of truth**: Component manifest validated by `component-manifest.schema.json`.

**Classification/retention**: Public engineering metadata; Git retained.

**Reconciliation**: `structure-check` compares manifest, repository paths, Make adapters and tests.

## Entity: ComponentActionBinding

Joins a component to a workflow action.

| Field | Type | Rules |
|-------|------|-------|
| `component_id` | ComponentBoundary ID | Required |
| `action` | enum | `bootstrap`, `fmt`, `fmt-check`, `type-check`, `lint`, `test`, `build`, optionally `migrate` |
| `adapter` | path/target reference | Must resolve inside component and be non-empty |
| `required` | boolean | Mandatory bindings cannot be skipped |
| `evidence_type` | enum | `formatted-files`, `static-report`, `test-count`, `coverage-report`, `image`, `asset-archive`, `migration-result` |
| `minimum_evidence` | object | For test actions includes `executed_tests >= 1` |
| `timeout_seconds` | positive integer | Bounded per action; exact values finalized in tasks/config |

**Identity**: `(component_id, action)` is unique.

**Failure rule**: Failure of a required binding fails the run; later required bindings become `SKIPPED` with safe reason, never `PASSED`.

## Entity: ToolchainRequirement

Represents a supported tool or scanner and its version source.

| Field | Type | Rules |
|-------|------|-------|
| `tool` | string | Unique within scope |
| `exact_version` | string | Required for CI/scanners; language compatibility may also declare a range |
| `version_source` | path | Repository file or lock file that owns the value |
| `affected_components` | component IDs | Non-empty |
| `install_policy` | enum | `preinstalled-required`, `locked-package-manager`, `verified-download`, `pinned-container` |
| `integrity_reference` | checksum/digest/SHA | Required for downloaded binaries, containers and Actions |

**Invariants**:

- Local and CI checks read the same version source.
- Missing or unsupported versions fail before component actions.
- Workflow commands never silently install or upgrade a toolchain.
- Cache hits never replace version or integrity validation.

## Entity: ConfigurationDefinition

Describes a configuration name without containing a real value.

| Field | Type | Rules |
|-------|------|-------|
| `name` | uppercase identifier | Unique |
| `value_type` | enum | `string`, `integer`, `boolean`, `url`, `duration`, `enum` |
| `required_modes` | set | Subset of `local`, `test`, `prod` |
| `sensitivity` | enum | `public`, `internal`, `secret`, `personal`, `financial` |
| `safe_placeholder` | string | Must be synthetic and unusable; secret placeholders cannot match provider credential formats |
| `description` | string | Non-empty and safe for public docs |
| `owner_component` | component ID | Required |

**Invariants**:

- No real value is stored in the definition or committed examples.
- Logs and validation errors mention `name`, never the supplied value.
- `.env`, `.env.*` are ignored except safe `*.example` files.
- Production-required security/persistence values have no working default.

## Entity: EnvironmentSelection

Represents environment selection for migration and future deployment commands.

| Field | Type | Rules |
|-------|------|-------|
| `mode` | enum | Exactly lowercase `local`, `test`, `prod` |
| `input_origin` | enum | `make-command-line`, `omitted`, `shell-environment`, `file`, `legacy-variable` |
| `effective_mode` | enum | Omitted becomes `local`; only command-line input can select `test` or `prod` |
| `config_reference` | path/reference | Selected only after mode validation; real file remains ignored |
| `approval_required` | boolean | `true` only for `prod` |
| `preflight_state` | enum | `requested`, `validated`, `approved`, `connection_allowed`, `rejected` |

**State transitions**:

```text
omitted/requested ──> validated(local) ──> connection_allowed
explicit test      ──> validated(test)  ──> connection_allowed
explicit prod      ──> validated(prod)  ──> approved ──> connection_allowed
invalid/source escalation/approval missing ─────────────> rejected
```

**Critical invariant**: `rejected` occurs before reading target configuration, resolving target DNS, starting containers or opening a network connection.

## Entity: ProductionApproval

| Field | Type | Rules |
|-------|------|-------|
| `approval_type` | enum | `interactive-phrase`, `protected-environment` |
| `action` | string | Must equal requested action |
| `commit_sha` | string | Required for non-interactive approval |
| `run_id` | string | Required for non-interactive approval |
| `approval_reference` | string | Safe audit reference; never a token |
| `approved_at` | timestamp | UTC |

Approval is ephemeral and single-use for its bound action/commit/run. The approval token or reviewer credential is never logged or stored by the workflow model.

## Entity: MigrationOwner

| Field | Type | Rules |
|-------|------|-------|
| `component_id` | enum | `api-service` or `billing-service` in SF01 |
| `order` | integer | Unique; API precedes billing |
| `version_path` | repository-relative path | Must remain inside owner component |
| `expected_heads` | positive integer | Exactly `1` after initialization |
| `owns_database` | boolean | Must be true |
| `backout_runbook` | path | Required and link-valid |

`admin-service` is explicitly not a migration owner. Cross-owner foreign keys and direct storage access are forbidden.

## Entity: MigrationPlan

| Field | Type | Rules |
|-------|------|-------|
| `owner` | MigrationOwner | Required |
| `mode` | EnvironmentSelection | Required for apply; not required for offline check |
| `current_head` | revision ID or `base` | Derived |
| `target_head` | revision ID or `base` | Derived |
| `pending_count` | non-negative integer | Zero allowed only after initialized graph validation |
| `forward_evidence` | reference | Required for changed migrations |
| `backout_evidence` | reference | Required for changed migrations |
| `retry_evidence` | reference | Required for changed migrations |

No business tables are created by SF01. CI migration evidence uses an isolated PostgreSQL 15 instance and synthetic credentials.

## Entity: WorkflowRun

| Field | Type | Rules |
|-------|------|-------|
| `run_id` | UUID/opaque unique ID | Unique per invocation |
| `action` | command name | Required |
| `mode` | effective mode or null | Null when not applicable |
| `started_at` | timestamp | UTC |
| `completed_at` | timestamp or null | Set on terminal state |
| `status` | enum | `PENDING`, `RUNNING`, `PASSED`, `FAILED` |
| `step_results` | ordered list | At least one for non-help actions |

**State transition**: `PENDING → RUNNING → PASSED|FAILED`; terminal states are immutable.

**Retention/classification**: Ephemeral operational evidence, no secrets or personal data. Local output is not committed; CI logs/artifacts follow repository retention settings defined during implementation.

## Entity: WorkflowStepResult

| Field | Type | Rules |
|-------|------|-------|
| `schema_version` | semantic version | Required |
| `run_id` | WorkflowRun ID | Required |
| `action` | string | Required |
| `component` | component ID or `repository` | Required |
| `phase` | string | Stable short identifier |
| `status` | enum | `STARTED`, `PASSED`, `FAILED`, `SKIPPED` |
| `code` | stable error/status code | Required for failed/skipped; safe success code otherwise |
| `duration_ms` | non-negative integer | Required on terminal step event |
| `message` | string | Human-readable, redacted safe summary |

## Entity: CIGate

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | Unique; required job is `quality-gate` |
| `triggers` | set | PR/push to `master` and `master-dev`, manual; merge group when enabled |
| `root_target` | string | `ci` |
| `blocking` | boolean | Always true for required gate |
| `permissions` | map | `contents: read`; all unspecified permissions none |
| `evidence` | list | Frozen bootstrap, format, independent type-check, lint/boundary, tests, contracts, offline plus isolated PostgreSQL migrations, secrets/dependencies/images, build/smoke |
| `retention_policy` | reference | CI setting; must exclude secrets |

**Invariants**:

- CI project logic invokes only root workflow targets.
- No production deployment, publishing or secret-bearing action is allowed.
- A failed required step cannot use `continue-on-error`.
- Required job name remains stable through rollback.

## Entity: SharedContractArtifact

| Field | Type | Rules |
|-------|------|-------|
| `contract_id` | string | Unique |
| `owner` | component/maintainer | Required |
| `version` | semantic version | Required |
| `format` | enum | JSON Schema, OpenAPI, event schema, Markdown developer contract |
| `compatibility` | enum | `backward-compatible`, `breaking-new-version` |
| `deprecated_at` | date or null | Required only when deprecated |
| `replacement` | contract reference or null | Required when deprecated |

Generated consumers are reproducible outputs of the contract source and are not independent facts. Contract drift fails CI.
