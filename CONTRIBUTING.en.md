[中文](CONTRIBUTING.md) | **English**

# Contributing

TokenMarket is a proprietary repository. This page is the internal loop for changing code, naming branches, and opening PRs. Canonical detail: [ops/runbooks/workflow.md](ops/runbooks/workflow.md).

## Loop

1. Branch from healthy `master-dev` (production hotfixes from `master`).
2. Spec and tests before implementation (constitution: test evidence before merge).
3. Root entry: `make fmt`, `make lint`, `make test`; reproduce `make ci` before merge.
4. Use [Conventional Commits](https://www.conventionalcommits.org/) (for example `feat: add gateway health check`, `docs: classify documentation hub`).
5. PRs merge to `master-dev`. Promote to `master` after test-environment verification.

## Branches

| Kind | Form | Merges to |
|------|------|-----------|
| Production line | `master` (fixed) | — |
| Test line | `master-dev` (fixed) | — |
| Spec Kit feature | `NNN-short-kebab` = only `specs/NNN-short-kebab/` | `master-dev` |
| Product change without Spec Kit | `feat/<slug>` | `master-dev` |
| Bugfix | `fix/<slug>` | `master-dev` |
| Production hotfix | `hotfix/<slug>` (from `master`) | `master`, then merge back |
| Docs / chore / refactor | `docs\|chore\|refactor/<slug>` | `master-dev` |

Rules: lowercase ASCII kebab-case; prefer ≤ 50 characters; do not encode `local` / `test` / `prod` in the branch name. Do not invent `NNN-...` without a matching `specs/NNN-.../` directory. Do not use `feat/002-...` when a numbered spec already exists.

Environment is always explicit `mode=local|test|prod`. Never infer it from the branch name.

## PRs should include

- Scope and linked spec / issue
- Verification evidence (commands and results)
- Contract, schema, and security impact
- Rollout and rollback notes
- Screenshots or equivalent for visible frontend changes

## Quality gates

GitHub Actions only invokes `make ci`. Do not duplicate component commands in workflow YAML. Do not commit secrets, `.env.local`, or production data.

A new service, store, protocol, or cross-service dependency needs an [ADR](docs/decisions/README.en.md).
