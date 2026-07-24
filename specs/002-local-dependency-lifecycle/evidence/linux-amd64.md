# Linux x86_64 Evidence (T069)

**Status**: **PASS**

**Validation date**: 2026-07-24

**Harness commit**: `21bbd96e168a9a0ed84ca8cab0e8eba451c6bf5a`

## Execution environment

| Item | Value |
|------|--------|
| Execution topology | Windows host + WSL2 Ubuntu + Docker Desktop Linux engine (**not** bare-metal Linux) |
| Linux kernel | 6.18.33.2-microsoft-standard-WSL2 |
| Distribution | Ubuntu 24.04.4 LTS (noble) |
| Host architecture | x86_64 |
| Docker Client | 29.5.3 |
| Docker Server Engine | 29.5.3 |
| Docker Desktop | 4.77.0 (228796) |
| Docker Compose | v5.1.4 |
| Docker engine platform | linux / x86_64 |
| CPUs | 12 |
| `make toolchain-check` | **PASS** |
| pytest asyncio mode | Mode.AUTO |

Expected container platform for native identity checks: `linux/amd64`.

## Harness command

```bash
uv run --project tools/workflow --locked pytest \
  -c tools/workflow/pyproject.toml \
  tests/workflow/test_local_env_performance.py \
  tests/workflow/test_local_env_persistence.py \
  tests/workflow/test_local_env_integration.py \
  tests/workflow/test_local_env_recovery.py \
  -v -s --tb=short
```

Committed shared harness sources: `tests/workflow/conftest.py` (`PerformanceHarness`) plus the suites above (including Desktop/WSL stabilization committed at the harness SHA).

## Matrix result

| Metric | Value |
|--------|--------|
| collected | 25 |
| passed | 25 |
| failed | 0 |
| skipped | 0 |
| exit code | 0 |
| total duration | 1240.87s |

## Cold trials (SC-001)

| Metric | Value |
|--------|--------|
| success | 20/20 |
| readiness within 60 seconds | 20/20 |
| required threshold | at least 19/20 |
| slowest readiness | 6.29s |
| slowest wall time | 8.79s |

Image pull timing is excluded from the readiness window by harness construction.

## Healthy repeats (SC-002)

| Metric | Value |
|--------|--------|
| success | 10/10 |
| within 15 seconds | 10/10 |
| slowest wall time | 3.09s |
| registry pulls | none (`pulled=False` for all repeats) |
| resource identities | stable |

## Persistence

| Check | Result |
|-------|--------|
| ten real Compose down/start cycles | **PASS** |
| every down/start transition | **PASS** |
| PostgreSQL marker retained after all cycles | **PASS** |
| empty Redis tolerance tests | **PASS** |
| no unexpected schema/migration/seed behavior | **PASS** |

## Other acceptance checks

| Check | Result |
|-------|--------|
| native linux/amd64 image identity | **PASS** |
| image verification | **PASS** |
| signal and recovery suite | **PASS** |
| event-v2 envelope | **PASS** |
| event correlation | **PASS** |
| phase ordering | **PASS** |
| final PASSED/OK status | **PASS** |
| missing-image phase separation | **PASS** |
| bounded image-pull timeout | **PASS** |
| port-race classification (`PORT_CONFLICT` / reconcile / postgres) | **PASS** |

## Post-run state

| Check | Value |
|-------|--------|
| tmtest containers | 0 |
| tmtest networks | 0 |
| tmtest volumes | 0 |
| final git status | clean |
| `git diff --check` | **PASS** |

## Conclusion

**T069 PASS** on the committed shared performance harness at harness commit `21bbd96e168a9a0ed84ca8cab0e8eba451c6bf5a`.

Topology transparency: validation ran on **WSL2 Ubuntu + Docker Desktop Linux Engine**, not bare-metal Linux. Public `make dev` / `make dev-down` remain `SF02_NOT_READY` until all required release gates (including remaining dual-platform and usability rows) pass.
