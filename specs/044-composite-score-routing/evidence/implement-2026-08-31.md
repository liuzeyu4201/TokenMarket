# Evidence 044

`go test -race -count=1 -coverprofile` on 2026-08-31:

- `internal/domain/score`: ok, coverage 90.7%
- `internal/domain/passthrough`: ok, coverage 89.1%
- `internal/domain/qualify`: ok

Monotonic four-factor tests, conservative zeros, replay JSON, explore stays in qualified set, dedicated hard-filter never wins (20/20), remaining reservation then `NO_UPSTREAM`, policy snapshot unchanged for locked decisions.
