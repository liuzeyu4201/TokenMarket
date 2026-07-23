# Runbook: User registration (API Service)

**Owner**: API Service  
**Feature**: `003-user-registration-ui` / SF03  
**PII**: Never log or paste full phone numbers; use `request_id` and masked forms only.

## Client IP and rate limiting

Registration rate limits use **source IP** (and normalized phone after successful
normalize). IP resolution order in API Service:

1. First hop of `X-Forwarded-For` (leftmost), if present
2. Otherwise the direct peer address from the ASGI connection

**Trust assumption**: only a trusted reverse proxy / ingress may set or overwrite
`X-Forwarded-For`. Clients that can spoof this header against an untrusted edge can
bypass or amplify per-IP limits. For local development, peer is typically `127.0.0.1`.
Production must terminate TLS at a trusted edge that strips untrusted XFF and injects
the real client address.

Phone-dimension limits never use the raw input string—only the normalized 11-digit CN
mobile—so invalid numbers only consume the IP bucket (FR-020a).

## Signals

| Signal | Metric / code | Severity |
|--------|---------------|----------|
| Elevated failure rate | `tokenmarket_registration_attempts_total{result=~"internal_error\|service_unavailable"}` | warning |
| Service unavailable | result=`service_unavailable` or HTTP 503 | critical |
| Rate-limit backend down | `tokenmarket_rate_limit_backend_unavailable_total` | critical |
| Rate-limit floods | `tokenmarket_registration_rate_limited_total` | info (capacity/abuse) |
| Phone conflicts | business code `PHONE_ALREADY_REGISTERED` | info (normal) |

Alert rules: `ops/alerts/registration.yml`.

## Triage

1. Capture alert time range and sample `request_id` values (no phone numbers).
2. Check API Service liveness/readiness and `/metrics`.
3. If Redis unavailable: restore Redis; registration fails closed until Redis returns.
4. If PostgreSQL unavailable: restore DB; no partial users should exist (single short transaction).
5. For abuse/rate-limit floods: confirm thresholds (IP 20/15m, phone 5/15m); consider temporary IP blocks at edge.

## Recovery

- **DB down**: restore connectivity; re-run readiness; clients retry with **same** `Idempotency-Key` within 24h.
- **Redis down**: restore Redis; no data migration required for rate-limit keys.
- **Migration issues**: see `services/api-service/README.md` upgrade/downgrade notes; never auto-migrate on app start.

## Backup / restore

`users` and `registration_idempotency_records` inherit the API Service PostgreSQL platform backup. Soft-delete is not restore. See `ops/backup/README.md` for instance-level procedures.
