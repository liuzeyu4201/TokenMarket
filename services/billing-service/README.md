# Billing Service

TokenMarket 测试额度账本与报价服务。第二迁移所有者。V0.2 **没有**充值、真实支付、Escrow、提现或法币锚定。

Hub: [`docs/architecture/README.md`](../../docs/architecture/README.md).

## Ownership

- Owner: TokenMarket Engineering
- Type: Python FastAPI service
- Migration owner: yes (order 2)
- Owns: immutable ledger entries, quotes, recon tickets, unresolved cost cases

Undetermined cost is recorded as `unresolved`, never as 0. Prefer explicit upstream spend, else usage × versioned rates.

Contracts: `shared/contracts/ledger/v1/`, `shared/contracts/pricing/v1/`.

## Commands

```bash
make bootstrap
make fmt
make type-check
make lint
make test
make build
make migrate
```

## Readiness (SF02)

- `/health/live` is process-only.
- `/health/ready` is one owned `SELECT 1` against `DATABASE_URL` (2s, no retry). Failures name only `postgres` — no URLs or secrets.
