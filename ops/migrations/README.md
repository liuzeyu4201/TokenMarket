# Migration ownership

The migration owner registry lives in `ops/migrations/owners.json`. It declares
which services own Alembic migration graphs and the order in which they must be
applied.

## Owners

- `api-service` — order 1
- `billing-service` — order 2

## Non-owners

- `admin-service` — does not own or directly access migration storage
