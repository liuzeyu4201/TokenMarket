# Implementation evidence: 036-stream-file-async-affinity

**Date**: 2026-08-31

## Coverage

```
affinity       87.0%
endpcatalog    84.0%
passthrough    89.6%
```

`go test -race -count=1 ./internal/domain/affinity/ ./internal/domain/endpcatalog/ ./internal/domain/passthrough/` passed.

## Soak

Default CI: `TestSoakConcurrentSSE` (8 streams × 200ms).
Full 500 × 2h: `TOKENMARKET_SOAK_SSE=500 TOKENMARKET_SOAK_DURATION=2h go test -race ./internal/domain/passthrough/ -run Soak -count=1`

## Negatives

- SSE events a,b,c flushed in order; idle stall ends without blocking a second request; cancel observed in 1s.
- WebSocket Upgrade/Connection forwarded; 101 + echo; shared mode `DEDICATED_PROJECT_REQUIRED`.
- Content-Length oversize returns 413 and upstream receives 0 bytes; no `os.CreateTemp` / `ioutil.TempFile` in passthrough/affinity production sources.
- POST `/v1/files` registers `id` → Connection; GET pins `SelectConnection`; missing ID is `AFFINITY_NOT_FOUND` with zero Select/SelectConnection.
- Snapshot file reloads after new Table; same `request_id` usage end event is idempotent.
