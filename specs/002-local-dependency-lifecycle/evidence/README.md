# SF02 Evidence Index (T072)

Owner: repository workflow owner

Public activation of `make dev` / `make dev-down` and default event v2 requires **all** rows below to pass. Until then, public targets remain `SF02_NOT_READY`.

| Artifact | Task | Status |
|----------|------|--------|
| [quality-gates.md](./quality-gates.md) | T068 | **PASS** — toolchain through build + image-scan green (2026-07-22) |
| [linux-amd64.md](./linux-amd64.md) | T069 | **PASS** — 2026-07-24; harness `21bbd96`; 25/25 matrix (WSL2 Ubuntu + Docker Desktop Linux engine) |
| [macos-arm64.md](./macos-arm64.md) | T070 | **PASS** — 20/20 cold + 10/10 repeats on Darwin arm64 (2026-07-22) |
| [developer-usability.md](./developer-usability.md) | T071 | **Pending** — 10-person protocol (human owner) |
| ADR 002 implementation verification | T073–T074 | Design **Accepted**; verification **Pending** until dual-platform + T068–T071 |


## Quickstart scenarios (safe / current branch)

| Section | Scenario | Status this branch |
|---------|----------|--------------------|
| 1 | `make help` | **PASS** |
| 1 | `make toolchain-check` | **PASS** (T069 committed audit 2026-07-24) |
| 2 | `.env.example` / ignore policy | Documented; do not commit `.env.local` |
| 3–8 | Public `make dev` / `dev-down` cold start, repeat, stop, marker | **Blocked by design** (`SF02_NOT_READY` until T074); covered by guarded unit/integration tests |
| 9–10 | Automated `make test` SF02 coverage | Offline suite **PASS** (see quality-gates) |
| 11 | Dual-platform harness | **Linux T069 PASS** (2026-07-24, `21bbd96`); **macOS T070 PASS** (2026-07-22) |
| 12 | Evidence pack | This index |

## Related documents

- Spec / plan / tasks: `specs/002-local-dependency-lifecycle/`
- Runbook: `ops/runbooks/local-environment.md`
- ADR: `docs/decisions/002-local-compose-lifecycle.md`
- Digests: `ops/workflow/local-dependencies.json`

## Redaction rules

Never include secrets, full URLs with user-info, workspace paths, or raw Docker stderr. Aggregate timings and pass/fail only.
