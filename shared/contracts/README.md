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
| `repository-workflow/v2/` | Repository maintainers | 2.0.0 (activated T074) | JSON Schema / Markdown |
| `local-environment/v1/` | Repository and infrastructure maintainers | 1.0.0 | JSON Schema / Markdown |
| `deploy-environment/v1/` | Repository and infrastructure maintainers | 1.0.0 | Markdown |
| `user-registration/v1/` | API Service (user domain) | 1.0.0 | OpenAPI / Markdown |
| `phone-auth-session/v1/` | API Service (authentication domain) | 1.0.0 | OpenAPI / Markdown |

## Compatibility and deprecation status

- `repository-workflow/v1/service-health.openapi.yaml` 1.1.0 is a backward-compatible
  minor update: it adds only the API/Billing PostgreSQL 503 readiness response; the
  200 and liveness shapes are unchanged.
- `repository-workflow/v2/` versions the breaking `dev`/`dev-down` success/side-effect
  semantics and the standard-envelope workflow event. **Activated at T074** after every
  repository event consumer migrated and both-platform lifecycle evidence passed. The
  public runtime emits event v2 by default; historical `SF02_NOT_READY` fail-closed
  behavior is retained only as regression documentation. The immutable v1 Make/event
  artifacts and `emit_event_v1` remain through at least the next tagged release; no new
  consumer may target v1 during the deprecation window.
- `local-environment/v1/` owns the SF02 dependency set, URL grammar, workspace identity,
  lock, resource, probe, persistence and recovery rules; incompatible changes require a
  new version and synchronized consumers.
- `deploy-environment/v1/` owns the ADR 003 deploy stack (`make deploy` / `make deploy-down`),
  layered Compose assets, fixed test/prod project names, and the fail-closed Phase 1 gate;
  it must never expand `compose.local.yml` or allow `mode=local` deploy. Runtime activation
  is independent of SF02 public `dev` activation.
- `user-registration/v1/` owns `POST /api/v1/auth/register`, unified business envelope codes,
  CN mobile normalization rules, and privacy constraints for registration; breaking changes
  require a new version and synchronized API Service + frontend consumers.
- `phone-auth-session/v1/` owns phone OTP challenge, single active browser session, cookie/CSRF,
  SMS delivery port, and the four authentication operations
  (`POST /verification-challenges`, `POST /sessions`, `GET /session`, `DELETE /session`).
  `POST /verification-challenges` uses **202-before-dispatch** semantics: the neutral 202
  response and pending challenge are committed before the API Service internal dispatcher
  performs recipient-specific SMS delivery; the 202 does not assert account existence or
  actual delivery. Breaking changes require a new version and synchronized API Service +
  Frontend consumers; registration v1 semantics are not modified by this contract.
