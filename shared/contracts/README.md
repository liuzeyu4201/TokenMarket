# Shared Contracts

This directory holds versioned cross-component contracts. Contracts are the
single source of truth for HTTP APIs, events, shared schemas and developer
workflow definitions.

## Ownership and versioning

- Every contract has an owner, semantic version and compatibility statement.
- Consumers must generate types from these contracts; copied models are not
  allowed.
- Breaking changes require a new major/minor version and a documented
  deprecation window.

## Current contracts

| Path | Owner | Version | Format |
|------|-------|---------|--------|
| `repository-workflow/v1/` | Repository maintainers | 1.0.0 | JSON Schema / Markdown |
| `repository-workflow/v1/service-health.openapi.yaml` | Repository maintainers | 1.1.0 | OpenAPI |
| `repository-workflow/v2/` | Repository maintainers | 2.0.0 (pending activation) | JSON Schema / Markdown |
| `local-environment/v1/` | Repository and infrastructure maintainers | 1.0.0 | JSON Schema / Markdown |

## Compatibility and deprecation status

- `repository-workflow/v1/service-health.openapi.yaml` 1.1.0 is a backward-compatible
  minor update: it adds only the API/Billing PostgreSQL 503 readiness response; the
  200 and liveness shapes are unchanged.
- `repository-workflow/v2/` versions the breaking `dev`/`dev-down` success/side-effect
  semantics and the standard-envelope workflow event. It activates only after every
  repository event consumer migrates and both-platform lifecycle evidence passes; until
  then the runtime keeps the v1 `SF02_NOT_READY` fail-closed behavior. The immutable v1
  Make/event artifacts remain through at least the next tagged release after activation;
  no new consumer may target v1 during the deprecation window.
- `local-environment/v1/` owns the SF02 dependency set, URL grammar, workspace identity,
  lock, resource, probe, persistence and recovery rules; incompatible changes require a
  new version and synchronized consumers.
