[中文](README.md) | **English**

# API navigation

**Canonical HTTP / event contracts live in `shared/contracts/`**. This directory does not keep a second OpenAPI tree. The page classifies surfaces so `docs/api` and `shared/contracts` cannot drift.

Machine-readable contracts, owners, versions, and compatibility: [`shared/contracts/README.md`](../../shared/contracts/README.md).

## Contract first

A new API, event, or shared schema must be reviewed and versioned under `shared/contracts/<name>/vN/` before any producer or consumer is implemented. Frontend types are generated from contracts; a hand-copied “matches production today” model is not allowed.

- Minor version: optional fields only.
- Major version: breaking field, type, or behavior changes.
- Deprecated fields stay for at least one major version and are marked `deprecated`.

## V0.2 public surfaces

| Surface | Method / path | Contract |
|---------|---------------|----------|
| Register / login / session | `/api/v1/auth/*` | [`user-registration/v1`](../../shared/contracts/user-registration/v1/), [`phone-auth-session/v1`](../../shared/contracts/phone-auth-session/v1/), [`unified-phone-auth/v1`](../../shared/contracts/unified-phone-auth/v1/) |
| Workspace | `POST /api/v1/auth/workspace` | [`workspace-switch/v1`](../../shared/contracts/workspace-switch/v1/) |
| Authorization | `POST /api/v1/authorization/evaluate` | [`role-access-isolation/v1`](../../shared/contracts/role-access-isolation/v1/) |
| Project | `/api/v1/projects` | [`project/v1`](../../shared/contracts/project/v1/) |
| Binding | `/api/v1/projects/{id}/bindings` | [`provider-binding/v1`](../../shared/contracts/provider-binding/v1/) |
| Connection | `/api/v1/connections` | [`provider-connection/v1`](../../shared/contracts/provider-connection/v1/) |
| Project proxy keys | `/api/v1/projects/{id}/proxy-keys` | [`project-proxy-key/v1`](../../shared/contracts/project-proxy-key/v1/) |
| Native data plane | `/openai/*` · `/anthropic/*` · `/vertex/*` | [`native-passthrough/v1`](../../shared/contracts/native-passthrough/v1/), [`endpoint-catalog/v1`](../../shared/contracts/endpoint-catalog/v1/) |
| Routing | gateway internal | [`route-decision/v1`](../../shared/contracts/route-decision/v1/) |
| Ledger / quotes | billing-service | [`ledger/v1`](../../shared/contracts/ledger/v1/), [`pricing/v1`](../../shared/contracts/pricing/v1/) |
| Admin | `/admin` + admin-service | [`admin-identity/v1`](../../shared/contracts/admin-identity/v1/), [`admin-console/v1`](../../shared/contracts/admin-console/v1/) |
| V0.1 Volcano compat | `POST /v1/proxy/volcano/chat/completions` | [`volcano-openai-compat/v1`](../../shared/contracts/volcano-openai-compat/v1/) |
| Health / metrics | `/health/live`, `/health/ready`, `/metrics` | [`repository-workflow`](../../shared/contracts/repository-workflow/) |

Successful native data-plane bodies keep each vendor’s protocol shape. Control-plane and **pre-proxy** failures use `{code,message,data,request_id,timestamp}`.

## Ownership

- The feature team that introduces a contract owns it. Cross-service contracts need review from both producer and consumer owners.
- Generated artifacts are committed under `shared/contracts/` with a pointer back to the source. Drift blocks the build.

Runtime behavior and recovery: [`ops/runbooks/`](../../ops/runbooks/README.md).
