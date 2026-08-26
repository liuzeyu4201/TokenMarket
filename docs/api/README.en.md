[中文](README.md) | **English**

# API navigation

**Canonical HTTP / event contracts live in `shared/contracts/`**. This directory does not keep a second OpenAPI tree. The page classifies surfaces so `docs/api` and `shared/contracts` cannot drift.

Machine-readable contracts, owners, versions, and compatibility: [`shared/contracts/README.md`](../../shared/contracts/README.md).

## Contract first

A new API, event, or shared schema must be reviewed and versioned under `shared/contracts/<name>/vN/` before any producer or consumer is implemented. Frontend types are generated from contracts; a hand-copied “matches production today” model is not allowed.

- Minor version: optional fields only.
- Major version: breaking field, type, or behavior changes.
- Deprecated fields stay for at least one major version and are marked `deprecated`.

## V0.1 public surfaces

| Surface | Method / path | Contract |
|---------|---------------|----------|
| Registration | `POST /api/v1/auth/register` | [`user-registration/v1`](../../shared/contracts/user-registration/v1/) |
| OTP challenge | `POST /api/v1/auth/verification-challenges` | [`phone-auth-session/v1`](../../shared/contracts/phone-auth-session/v1/) |
| Session | `POST /api/v1/auth/sessions`; `GET` / `DELETE /api/v1/auth/session` | same |
| Authorization | `POST /api/v1/authorization/evaluate` | [`role-access-isolation/v1`](../../shared/contracts/role-access-isolation/v1/) |
| Seller keys | `/api/v1/seller-keys` | see `specs/008`, `specs/009` (published with the feature tree) |
| Buyer proxy keys | `/api/v1/proxy-keys` | see `specs/010` |
| Public proxy | `POST /v1/proxy/volcano/chat/completions` | [`volcano-openai-compat/v1`](../../shared/contracts/volcano-openai-compat/v1/) |
| Internal credential validation | `POST /internal/v1/provider-credentials/validate` | [`volcano-key-validation/v1`](../../shared/contracts/volcano-key-validation/v1/) |
| Health / ready / metrics | `/health/live`, `/health/ready`, `/metrics` | [`repository-workflow`](../../shared/contracts/repository-workflow/) |

Successful Chat Completions and started SSE **stay OpenAI-shaped**. Management/business APIs and **pre-proxy** failures use the unified envelope `{code,message,data,request_id,timestamp}`.

## Ownership

- The feature team that introduces a contract owns it. Cross-service contracts need review from both producer and consumer owners.
- Generated artifacts are committed under `shared/contracts/` with a pointer back to the source. Drift blocks the build.

Runtime behavior and recovery: [`ops/runbooks/`](../../ops/runbooks/README.md) (registration, authentication, authorization, Volcano validation, Volcano compat, proxy alerts).
