# Migration Runbook

## Owner order

1. `api-service`
2. `billing-service`

## Backout

Each owner migration includes a downgrade path. To back out:

1. Identify the last applied revision.
2. Run `make migrate mode=<env>` with the target revision, or downgrade via Alembic.
3. Never edit an already applied migration file.

## Rollback

For production, use the same `mode=prod` plus approved production confirmation.
