# TokenMarket

Repository workflow baseline for the TokenMarket platform.

## Quick start

1. **Install toolchains**

   Versions are pinned in `.tool-versions`:

   - Go 1.25.12
   - Python 3.11.15
   - uv 0.11.3
   - Node 24.18.0
   - Docker Engine 29.5.3 or later

2. **Verify the toolchain**

   ```bash
   make toolchain-check
   ```

3. **Prepare locked dependencies**

   ```bash
   make bootstrap
   ```

4. **Create local configuration**

   ```bash
   cp .env.example .env.local
   # Edit .env.local with your local values; never commit it.
   ```

5. **Run the full CI gate locally**

   ```bash
   make ci
   ```

   The gate runs the fixed sequence:
   `toolchain-check → bootstrap → fmt-check → type-check → lint → test →
   migrate-check → migrate-integration-check → security-check → build →
   runtime-smoke → image-scan`.

## Public workflow targets

| Target | Purpose |
|--------|---------|
| `make dev` | Start local dependencies (blocked until SF02) |
| `make dev-down` | Stop local dependencies (blocked until SF02) |
| `make fmt` | Apply repository formatters |
| `make lint` | Run static analysis, type checks and boundary checks |
| `make test` | Run all component tests |
| `make build` | Build five service images and three asset bundles |
| `make migrate` | Apply reviewed migrations to selected environment |
| `make ci` | Local reproduction of the hosted `quality-gate` |

## Components

- [`services/proxy-gateway`](services/proxy-gateway/README.md) — Go ingress gateway
- [`services/api-service`](services/api-service/README.md) — Core API service
- [`services/billing-service`](services/billing-service/README.md) — Billing service
- [`services/admin-service`](services/admin-service/README.md) — Admin service
- [`frontend`](frontend/README.md) — React web frontend
- [`shared`](shared/README.md) — Versioned contracts and shared tooling
- [`infra`](infra/README.md) — Infrastructure definitions
- [`ops`](ops/README.md) — Operational runbooks and migration ownership

## Recovery

- `make help` shows stable targets and side effects.
- `ops/runbooks/workflow.md` covers CI recovery, cache contamination, scanner
  failures, failed-main review-revert, and GitHub ruleset configuration.
- Security exceptions must follow the format in `ops/runbooks/workflow.md`.
