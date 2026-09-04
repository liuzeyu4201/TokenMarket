[中文](QUICKSTART.md) | **English**

# TokenMarket local quick start

Overview: [README.en.md](README.en.md). Catalog: [docs/README.en.md](docs/README.en.md).

After one-time setup, daily work is two commands.

```bash
make start
make stop
```

- `make start`: start or reuse PostgreSQL, Redis, Grafana, and the five host processes (gateway, api, billing, admin, frontend).
- `make stop`: stop app processes first, then middleware; keep PostgreSQL/Redis data.
- Every start re-reads and validates `.env.local`. Managed config changes restart the affected apps so a healthy process never keeps stale env vars.
- Application processes always run on the host. They never join `infra/docker/compose.local.yml`.

> **Activation**
>
> The SF02 public lifecycle is active. Default `make start` / `make stop` start or stop middleware plus five host app processes. `make dev` / `make dev-down` manage middleware only.

## First-time setup

### 1. Check tools and install locked dependencies

```bash
make toolchain-check
make bootstrap
```

Required versions are in `.tool-versions`. A local Docker daemon is required to start middleware.

### 2. Create local configuration

```bash
cp .env.example .env.local
```

`.env.local` is gitignored. Generate three distinct local synthetic passwords:

```bash
python3 -c 'import secrets; print("tm_local_" + secrets.token_urlsafe(24))'
```

Replace the placeholders in:

```text
MODE=local
DATABASE_URL=postgresql://app:tm_local_<secret>@127.0.0.1:5432/tokenmarket
REDIS_URL=redis://default:tm_local_<different-secret>@127.0.0.1:6379/0
GRAFANA_URL=http://127.0.0.1:3000
GRAFANA_ADMIN_PASSWORD=tm_local_<third-secret>
```

Rules:

- Host must be the literal `127.0.0.1`, never `localhost`, `0.0.0.0`, or a LAN address.
- PostgreSQL, Redis, and Grafana ports come only from those three URLs.
- Shell `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, and `GRAFANA_HOST_PORT` do not override `.env.local`.
- Never commit `.env.local` or paste its contents into logs, issues, or PRs.

`make start` never generates or rotates these passwords. Auto-rotation would desync persisted PostgreSQL/Redis volumes from new credentials. When secrets must change, follow the recovery path and treat persisted dependencies together. The workflow stores only an irreversible app-config fingerprint; it never writes connection URLs or secrets into state files.

### 3. First start and explicit migrate

```bash
make start
make migrate
```

`make migrate` reads the local database URL from `.env.local` and applies migrations in owner order: API Service → Billing Service. Start does not migrate, reset, or seed the database.

Later daily starts:

```bash
make start
```

## Command map

### Daily

| Command | Behavior |
|---------|----------|
| `make start` | Start or reuse the full local environment |
| `make stop` | Stop the full local environment; keep PostgreSQL/Redis data |
| `make migrate` | Apply reviewed migrations; does not start the database |

### Advanced

| Command | When |
|---------|------|
| `make dev` | PostgreSQL, Redis, Grafana only |
| `make dev-down` | Stop middleware only; keep PostgreSQL/Redis data |
| `make start scope=apps` | Start or reuse the five host processes when middleware is already up |
| `make stop scope=apps` | Stop host processes owned by this workspace only |
| `make start scope=apps RESTART_PROCESS=1` | Force-restart host processes |

`scope=apps` is for diagnosis and partial development, not the daily path. Middleware-only operations stay on `make dev` / `make dev-down`. There is no `scope=stack` alias.

## Addresses

| Service | Default | Override |
|---------|---------|----------|
| PostgreSQL | `127.0.0.1:5432` | `.env.local` `DATABASE_URL` |
| Redis | `127.0.0.1:6379` | `.env.local` `REDIS_URL` |
| Grafana | `http://127.0.0.1:3000` | `.env.local` `GRAFANA_URL` |
| proxy-gateway | `http://127.0.0.1:8080` | `GATEWAY_HOST_PORT=…` |
| api-service | `http://127.0.0.1:8000` | `API_HOST_PORT=…` |
| billing-service | `http://127.0.0.1:8001` | `BILLING_HOST_PORT=…` |
| admin-service | `http://127.0.0.1:8002` | `ADMIN_HOST_PORT=…` |
| frontend | `http://127.0.0.1:5173` | `FRONTEND_HOST_PORT=…` |

App port example:

```bash
make start scope=apps API_HOST_PORT=18000 FRONTEND_HOST_PORT=15173
```

The frontend API base URL follows the current API port.

## After a successful start

```bash
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

Pages:

- Home: `http://127.0.0.1:5173/`
- Register: `http://127.0.0.1:5173/register`
- Login: `http://127.0.0.1:5173/login`
- Projects (session required): `http://127.0.0.1:5173/projects`
- Connections / supply: `/connections` · `/supply`
- Admin login: `http://127.0.0.1:5173/admin/login`
- Grafana: `http://127.0.0.1:3000`

Native data plane (proxy key, not the browser session):

- `http://127.0.0.1:8080/openai/v1/chat/completions`
- `http://127.0.0.1:8080/anthropic/v1/messages`
- V0.1 Volcano compat: `POST http://127.0.0.1:8080/v1/proxy/volcano/chat/completions`

`/health/live` means the process is up. Database-backed features also need readiness and a successful migrate.

## Failure and recovery

Start output includes stage, component, a stable error code, and the next recovery action. After a fix, rerun the same command.

| Code | Meaning | Recovery |
|------|---------|----------|
| `SF02_NOT_READY` | Historical diagnostic; must not appear on the public path | Upgrade to the activated toolchain; check for obsolete scripts |
| `INVALID_CONFIG` | `.env.local` missing, still placeholder, or illegal URL | Fix against the template and retry |
| `TOOL_MISSING` | Tool or Docker daemon unavailable | Start/install the declared version and retry |
| `PORT_CONFLICT` | Port held by another process | Free the port; middleware ports change only via URLs; app ports use the matching variable |
| `DEPENDENCY_NOT_READY` | Middleware readiness probe timed out | Read the safe diagnostic, fix, retry `make start` |
| `APP_NOT_READY` | One or more app processes missed liveness | Open the runtime log path printed in the output |

If `.env.local` or an app port changes, the next `make start` prints `action=restart reason=config_changed` and relaunches the affected processes.

App stdout/stderr lives in a workspace-hash-isolated runtime directory, not in the repository.

## Do not start this way

- Do not run `docker compose -f infra/docker/compose.local.yml up` directly.
- Do not add business services to `compose.local.yml`.
- Do not run `make deploy mode=local`; deploy allows only `mode=test|prod`.
- Do not override middleware ports from the shell; edit the matching URL in `.env.local`.
- Do not use in-component start commands as the daily entry; they are for maintenance and diagnosis.

Test/prod full stack:

```bash
make build
make deploy mode=test
```

More:

- `make help`
- `ops/runbooks/local-environment.md`
- `ops/runbooks/deploy.md`
- `README.en.md`
