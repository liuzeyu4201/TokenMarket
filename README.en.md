[中文](README.md) | **English**

# TokenMarket

> Make idle AI Coding Plan quota liquid.

TokenMarket is a **real-time matching and proxy platform for AI Coding Plan quota**: sellers onboard existing quota, buyers call through a platform-issued proxy key, and the gateway forwards OpenAI-compatible Chat Completions upstream (Volcano Ark only in V0.1).

This repository is the **monorepo** that implements that product. It is in **V0.1 technical validation**: the proxy path and identity/key APIs are in place; billing/matching, additional providers, and full product UI remain later versions.

## Contents

- [Current scope](#current-scope)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Repository layout](#repository-layout)
- [Public commands](#public-commands)
- [Documentation](#documentation)
- [Security](#security)
- [License](#license)

## Current scope

**In place**

- One-command local lifecycle: middleware (PostgreSQL 15, Redis 7, Grafana OSS) plus five host processes
- Registration, phone-verified login, session cookies, RBAC, and self-trade isolation
- Seller key onboard / pause / resume / revoke (API); buyer proxy key issue / list / revoke (API)
- Public proxy: `POST /v1/proxy/volcano/chat/completions` (JSON and SSE)
- Key-pool rotation, upstream capacity protection, seller-key health checks, usage observation, structured request logs
- Grafana V0.1 proxy overview dashboard and fail-closed secret/dependency scans
- Layered Compose for test/prod: `make deploy mode=test|prod`

**Out of V0.1**

- Pricing, balance debit, escrow, TMP credits, withdrawals, and invoices (billing service remains a scaffold)
- Zhipu and other providers; embeddings / non-chat endpoints
- Full seller listing, buyer top-up, and admin review Web product pages (frontend today: register / login / dashboard placeholder)
- Kafka in the local `make dev` dependency set; business services inside `compose.local.yml`

Product intent and versioning live in [`项目开发/产品需求文档（PRD）.md`](项目开发/产品需求文档（PRD）.md) and [`项目开发/产品迭代路线图.md`](项目开发/产品迭代路线图.md). Feature specs live in [`specs/`](specs/) and [`项目开发/V0.1/V0.1_0712/specs/`](项目开发/V0.1/V0.1_0712/specs/README.md).

## Architecture

```text
  Browser / OpenAI-compatible client
           │
           ├─ UI ──────────────────────────────► frontend :5173
           │                                      │ /api/v1 (session)
           │                                      ▼
           │                               api-service :8000
           │                               register · login · authz
           │                               seller keys · proxy keys
           │
           └─ POST /v1/proxy/volcano/chat/completions
                                              │
                                       proxy-gateway :8080
                                       auth · pick key · forward · observe
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                  billing-service      admin-service         Volcano upstream
                  :8001 scaffold       :8002 scaffold
                         │
              PostgreSQL · Redis · Grafana :3000
```

- **proxy-gateway** (Go / Gin): sole ingress for proxied AI traffic.
- **api-service** (Python / FastAPI): owner of users, authorization, and keys; first migration owner.
- **billing-service** (Python / FastAPI): second migration owner; no money loop in V0.1.
- **admin-service** (Python / FastAPI): admin scaffold; no database ownership.
- **frontend** (React 18 / Vite): single web app.
- **shared/contracts**: versioned HTTP / event / workflow contracts, defined before consumers.

Boundaries and data flow: [`docs/architecture/`](docs/architecture/README.en.md). Highest engineering constraint: the [constitution](.specify/memory/constitution.md).

## Quick start

Toolchain pins are in [`.tool-versions`](.tool-versions): Go 1.25.14, Python 3.11.15, Node 24.18.0, uv 0.11.3. Middleware needs a local Docker daemon.

```bash
make toolchain-check
make bootstrap
cp .env.example .env.local   # replace the three tm_local_ placeholders with distinct synthetic secrets
make start
make migrate
```

Day-to-day after that:

```bash
make start
make stop
```

First-time passwords, ports, and recovery codes: [`QUICKSTART.en.md`](QUICKSTART.en.md). Verify:

```bash
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

| Surface | URL |
|---------|-----|
| Frontend | http://127.0.0.1:5173 |
| Register / login / dashboard | `/register` · `/login` · `/dashboard` |
| Gateway liveness | http://127.0.0.1:8080/health/live |
| API readiness | http://127.0.0.1:8000/health/ready |
| Grafana | http://127.0.0.1:3000 |
| Public proxy | `POST http://127.0.0.1:8080/v1/proxy/volcano/chat/completions` |

Application processes run on the host. They **never** join `infra/docker/compose.local.yml`.

## Repository layout

```text
.
├── services/proxy-gateway   # Go gateway: health, metrics, Volcano proxy
├── services/api-service     # user / authz / key APIs, migration order 1
├── services/billing-service # billing scaffold, migration order 2
├── services/admin-service   # admin scaffold
├── frontend                 # React 18 frontend
├── shared/contracts         # versioned contracts (canonical, machine-readable)
├── infra                    # Compose, Grafana, image assets
├── ops                      # runbooks, alerts, migration ownership
├── tools/workflow           # workflow CLI behind the root Makefile
├── tests/workflow           # root workflow contract tests
├── specs                    # Spec Kit features and evidence
├── docs                     # documentation hub (catalog + ADRs)
├── 产品调研                 # market, competitors, business plan (canonical)
└── 项目开发                 # PRD, roadmap, engineering standards (canonical)
```

## Public commands

The root [`Makefile`](Makefile) is the only public entry. `make help` prints purpose, side effects, and recovery.

| Command | Purpose |
|---------|---------|
| `make start` / `make stop` | **Local default**: middleware + five host processes; reloads `.env.local` every start |
| `make dev` / `make dev-down` | PostgreSQL / Redis / Grafana only |
| `make start scope=apps` | App processes only when middleware is already up |
| `make deploy` / `make deploy-down` | Test/prod full stack; `mode=test\|prod` required |
| `make fmt` / `make lint` / `make test` | Format, static analysis, all tests |
| `make build` | Five service images and three deterministic asset bundles |
| `make migrate` | Reviewed Alembic migrations in owner order |
| `make ci` | Same sequence as GitHub Actions `quality-gate` |
| `make bootstrap` / `make type-check` | Locked dependencies; standalone type-check |

Layers: local = host apps + middleware; test/prod = `make build` then `make deploy mode=…`. Environment is **never** inferred from the Git branch name.

`.github/workflows/ci.yml` only invokes `make ci`. Project logic stays in the Makefile and `tools/workflow/`.

## Documentation

Catalog and language rules: [`docs/README.en.md`](docs/README.en.md) · [中文](docs/README.md)

| Reader | Start here |
|--------|------------|
| First run | [QUICKSTART.en.md](QUICKSTART.en.md) · [中文](QUICKSTART.md) |
| Change code, open a PR | [CONTRIBUTING.en.md](CONTRIBUTING.en.md) · [中文](CONTRIBUTING.md) |
| Architecture and ADRs | [docs/architecture](docs/architecture/README.en.md) · [docs/decisions](docs/decisions/README.en.md) |
| HTTP contracts | [docs/api](docs/api/README.en.md) → [`shared/contracts/`](shared/contracts/README.md) |
| Product and research | [docs/product](docs/product/README.en.md) |
| Local / deploy recovery | [ops/runbooks](ops/runbooks/README.md) |
| Report a security issue | [SECURITY.md](SECURITY.md) |

## Security

- Real config lives only in ignored `.env.local`; [`.env.example`](.env.example) holds unusable placeholders.
- gitleaks, govulncheck, pip-audit, and npm audit **fail closed**.
- Production actions require explicit `mode=prod` and independent approval.
- Seller upstream keys use authenticated encryption; logs and errors must not contain full credentials.

Details: [SECURITY.md](SECURITY.md) and [`ops/runbooks/workflow.md`](ops/runbooks/workflow.md).

## License

This repository is licensed under the [Apache License 2.0](LICENSE). Copyright and attribution are in [NOTICE](NOTICE).
