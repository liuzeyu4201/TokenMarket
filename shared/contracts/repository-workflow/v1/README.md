# Repository Workflow Contracts v1

This directory contains the runtime copies of the frozen design contracts for
TokenMarket's repository workflow baseline.

## Authoritative source

The authoritative source for these contracts is:

```text
specs/001-repository-workflow-baseline/contracts/
```

Any change to these runtime copies must be driven by a reviewed change to the
authoritative source under `specs/001-repository-workflow-baseline/contracts/`.

The JSON Schema runtime copies carry a top-level `schema_version` annotation
(`1.0.0`) in addition to the contents of the authoritative source files. This
annotation is ignored by JSON Schema validators and is used by repository tests
to confirm the runtime contract version.

## Contracts

| File | Purpose |
|------|---------|
| `component-manifest.schema.json` | JSON Schema for `ops/workflow/components.json` |
| `workflow-event.schema.json` | JSON Schema for workflow step JSONL events |
| `migration-manifest.schema.json` | JSON Schema for `ops/migrations/owners.json` |
| `service-health.openapi.yaml` | Minimal operational health endpoints for service scaffolds |
| `make-workflow.md` | Root Makefile public target and aggregate contract |
| `environment-mode.md` | `mode=local\|test\|prod` selection and approval contract |
| `ci-gates.md` | Continuous integration quality gate contract |

## Version

**schema_version**: `1.0.0`
