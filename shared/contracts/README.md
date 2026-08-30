# Shared Contracts

This directory holds versioned cross-component contracts. Contracts are the
single source of truth for HTTP APIs, events, shared schemas and developer
workflow definitions.

Human-readable catalog: [`docs/api/README.md`](../../docs/api/README.md) (中文) · [`docs/api/README.en.md`](../../docs/api/README.en.md) (English). Do not copy OpenAPI trees into `docs/api/`.

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
| `role-access-isolation/v1/` | API Service (authorization domain) | 1.0.0 | OpenAPI / Markdown |
| `volcano-key-validation/v1/` | Proxy Gateway (provider validation) | 1.0.0 | OpenAPI / Markdown |
| `volcano-openai-compat/v1/` | Proxy Gateway (Chat Completions adapter) | 1.0.0 | OpenAPI / Markdown |
| `endpoint-catalog/v1/` | Proxy Gateway (V0.2 Endpoint Catalog) | 1.0.0 | JSON Schema / JSON / Markdown |
| `native-passthrough/v1/` | Proxy Gateway (native same-protocol kernel, SF18+) | 1.0.0 | Markdown |
| `project/v1/` | API Service (Project domain, SF10+) | 1.1.0 | OpenAPI |
| `provider-binding/v1/` | API Service (Provider Binding, SF11+) | 1.0.0 | OpenAPI |
| `project-proxy-key/v1/` | API Service (Project proxy Key, SF12+) | 1.0.0 | OpenAPI |
| `provider-connection/v1/` | API Service (Provider Connection, SF14+) | 1.3.0 | OpenAPI |
| `route-decision/v1/` | Proxy Gateway (routing decision, SF23+) | 1.0.0 | JSON Schema |
| `usage/v1/` | Billing Service (usage observation, SF26+) | 1.0.0 | JSON Schema |
| `pricing/v1/` | Billing Service (versioned rates, SF27+) | 1.0.0 | JSON Schema |
| `ledger/v1/` | Billing Service (immutable ledger, SF28+) | 1.0.0 | JSON Schema |
| `audit/v1/` | Admin Service (audit events, SF30+) | 1.0.0 | JSON Schema |
| `usage-outbox/v1/` | Proxy Gateway (usage outbox, SF04) | 1.0.0 | JSON Schema |
| `unified-phone-auth/v1/` | API Service (unified phone auth, SF06) | 1.0.0 | OpenAPI |
| `single-session-auth/v1/` | API Service (single-session hardening, SF07) | 1.0.0 | OpenAPI |
| `web-design-system/v1/` | Frontend (design system and app shell, SF08) | 1.0.0 | Markdown |
| `workspace-switch/v1/` | API Service (workspace switch, SF09) | 1.0.0 | OpenAPI |

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
- `endpoint-catalog/v1/` is the V0.2 freeze-day (2026-08-31) unique source for OpenAI,
  Anthropic, and Google Vertex model data-plane scope (ADR 005). Published versions only
  add compatible records/fields; `catalog_major` mismatch fail-closes consumers. Preview/beta
  require Project opt-in. Control-plane paths are cataloged and rejected. Volcano V0.1
  contracts stay independent. `project/v1` 1.1.0 is a backward-compatible expansion
  implemented by SF10 (lifecycle writers; PATCH still has no mode). `provider-connection/v1`
  1.1.0 is a backward-compatible expansion implemented by SF14 (encrypted credentials,
  no plaintext read-back). 1.2.0 adds verify, health, and capability snapshots (SF15).
  1.3.0 adds supply lifecycle and mode lock (SF16).
  `native-passthrough/v1` is the SF18 same-protocol kernel (no cross-protocol
  conversion). Route/usage/pricing/ledger/audit writers land in later SFs.
- `deploy-environment/v1/` owns the ADR 003 deploy stack (`make deploy` / `make deploy-down`),
  layered Compose assets, fixed test/prod project names, and the fail-closed Phase 1 gate;
  it must never expand `compose.local.yml` or allow `mode=local` deploy. Runtime activation
  is independent of SF02 public `dev` activation.
- `user-registration/v1/` owns historical `POST /api/v1/auth/register` envelope codes,
  CN mobile normalization, and privacy constraints. SF06 (`unified-phone-auth/v1`)
  requires the public register path to reject without occupancy enumeration
  (`AUTH_VERIFICATION_REQUIRED`); new accounts are created only via OTP + profile completion.
- `phone-auth-session/v1/` owns phone OTP challenge, single active browser session, cookie/CSRF,
  SMS delivery port, and the four authentication operations
  (`POST /verification-challenges`, `POST /sessions`, `GET /session`, `DELETE /session`).
  `POST /verification-challenges` uses **202-before-dispatch** semantics: the neutral 202
  response and pending challenge are committed before the API Service internal dispatcher
  performs recipient-specific SMS delivery; the 202 does not assert account existence or
  actual delivery. Breaking changes require a new version and synchronized API Service +
  Frontend consumers; registration v1 semantics are not modified by this contract.
- `web-design-system/v1/` owns the SF08 foundation component state catalog (button,
  field, notice, dialog, table, page states). Breaking visual/interaction changes
  require a new version and synchronized frontend pages.
- `workspace-switch/v1/` owns session workspace (`buyer`/`seller`) and the rule
  that authorization uses the session workspace only. Breaking changes require a
  new version and synchronized API Service + frontend consumers.
- `provider-binding/v1/` owns Project×protocol Binding draft/validate/publish,
  single active version, same-protocol constraint, and dedicated degrade
  without shared-pool fallback. Breaking changes require a new version.
- `project-proxy-key/v1/` owns Project-scoped buyer proxy keys, one-time secret
  delivery, HMAC-at-rest, and protocol/model/CIDR/quota/expiry intersection.
  Breaking changes require a new version.
- `provider-connection/v1` 1.3.0 expands create with list/replace/delete/internal unwrap,
  verify, health, capability snapshots, and supply lifecycle (mode lock, pause/drain),
  while keeping no-plaintext-readback. Breaking credential-readback would require a new
  major version.
