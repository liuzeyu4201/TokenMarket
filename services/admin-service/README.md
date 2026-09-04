# Admin Service

TokenMarket 独立管理员身份与运维面。无业务库所有权、无迁移。买家 Cookie 不能进入此后台。

Hub: [`docs/architecture/README.md`](../../docs/architecture/README.md).

## Ownership

- Owner: TokenMarket Engineering
- Type: Python FastAPI service
- Migration owner: no
- Isolated admin session (account / password / MFA), RBAC, catalog publish helpers

Contracts: `shared/contracts/admin-identity/v1/`, `shared/contracts/admin-console/v1/`.

Frontend mounts the shell at `/admin` (login: `/admin/login`).

## Commands

```bash
make bootstrap
make fmt
make type-check
make lint
make test
make build
```
