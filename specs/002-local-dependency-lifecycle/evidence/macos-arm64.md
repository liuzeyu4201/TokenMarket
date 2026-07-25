# macOS arm64 Evidence (T070)

**Status**: **PASS** (performance harness + named-volume cycles) on Darwin arm64 with Docker 29.5.3 / Compose 5.1.4 — 2026-07-22.

## Host

| Item | Value |
|------|--------|
| OS | Darwin arm64 |
| Container platform | linux/arm64 (native) |
| Docker Engine | 29.5.3 |
| Compose | 5.1.4 |
| Node (for toolchain-check) | 24.18.0 via `nvm use 24.18.0` |
| Python | 3.11.15 / uv workflow project |

## Harness commands (redacted)

```text
nvm use 24.18.0
uv run --project tools/workflow python -m pytest \
  -c tools/workflow/pyproject.toml \
  tests/workflow/test_local_env_performance.py -s
```

Also green: `test_ten_down_restart_cycles_retain_named_volumes`,
`test_empty_redis_tolerance_and_no_schema_actions`.

## Results (aggregate only)

| Check | Result |
|-------|--------|
| Cold batch (20 trials) | **20/20 PASSED**; readiness ~1.3–1.4s each (≪ 60s budget); ≥19 within 60s |
| Healthy repeats (10) | **10/10** within 15s (slowest ~0.73s); no registry pulls; stable container/network/volume identities |
| Named-volume down/restart cycles | **PASS** |
| Empty Redis / no schema actions | **PASS** |
| Native arm64 image identity | exercised via digest-pinned pull/start path |
| Loopback publishers | enforced by adapter + compose structure tests |
| Event-v2 parity | unit suite + lifecycle events (standard envelope) |

### Residual note

`test_real_compose_ten_cycles_retain_postgres_marker` can race when a concurrent
ADR 003 `tokenmarket-test` deploy stack holds host ports / repository labels.
T083 fixed deploy-label classification interference (`stack=deploy` skipped in
SF02 moved-workspace discovery). Marker cycle remains sensitive to host port
occupancy; not blocking SC-001/SC-002 performance evidence on this host.

## Conclusion

macOS arm64 lifecycle performance and persistence acceptance for T070 is
**PASS**. Linux x86_64 (T069) is **PASS**; usability protocol (T071) and public
activation (T074) completed 2026-07-25.
