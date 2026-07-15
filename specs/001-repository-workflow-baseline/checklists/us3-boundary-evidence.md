# US3 Boundary Evidence

**Feature**: specs/001-repository-workflow-baseline — 仓库工程工作流基线  
**Story**: US3 — 在明确的组件边界内开始开发  
**Recorded**: 2026-07-15

## 1. Structure Tests

`tests/workflow/test_structure.py` verifies:

- Every component has a non-empty `README.md`.
- Component paths stay inside the repository root.
- Declared `test_root` directories exist.
- Deliverables are one of the known artifact kinds.

Result: **4 passed, 0 failed**.

## 2. Contract Tests

`tests/workflow/test_contracts.py` verifies:

- `shared/contracts/_meta/contract-manifest.schema.json` exists.
- Each runtime contract in `shared/contracts/repository-workflow/v1/` carries
  `$schema` and `schema_version`.

Result: **2 passed, 0 failed**.

## 3. Boundary Tests

`tests/workflow/test_boundaries.py` verifies:

- `admin-service` does not bind the `migrate` action.
- No Python service imports another service's internal package.

Result: **2 passed, 0 failed**.

## 4. ADR Policy Tests

`tests/workflow/test_adr_policy.py` verifies:

- `docs/decisions/` exists.
- `docs/decisions/README.md` exists and is non-empty.
- `docs/decisions/001-github-actions-ci-adapter.md` exists.

Result: **3 passed, 0 failed**.

## 5. Codeowners

`.github/CODEOWNERS` assigns review owners to:

- Root workflow, CI and `CODEOWNERS` itself
- Each service boundary
- `shared/` contracts and validation
- `infra/` and `ops/` platform assets
- Security-sensitive configuration files

## 6. Component READMEs

All eight component directories contain READMEs documenting ownership,
responsibility and allowed dependencies:

- `services/proxy-gateway/README.md`
- `services/api-service/README.md`
- `services/billing-service/README.md`
- `services/admin-service/README.md`
- `frontend/README.md`
- `shared/README.md`
- `infra/README.md`
- `ops/README.md`

## 7. Sign-off

US3 implementation proves that every asset has a single correct location,
cross-service boundaries are enforced, contracts are versioned, and ADRs are
required for future structural changes.
