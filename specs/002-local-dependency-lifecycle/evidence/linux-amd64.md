# Linux x86_64 Evidence (T069)

**Status**: Pending — this implement session ran on **Darwin arm64** only. Linux x86_64 harness was not executed here.

## Required host

- Linux x86_64 with Docker Engine 29.5.3 + Compose 5.1.4
- Expected container platform: `linux/amd64`

## Required harness (not yet run)

From `tests/workflow/conftest.py` (`PerformanceHarness`):

1. 20 cold trials — at least 19 ready within 60s (image pull timing separate)
2. Ten healthy repeats within 15s each
3. Ten persistence cycles with PostgreSQL marker retention
4. Native image identity (linux/amd64 child digest)
5. Signal/recovery and standard event-v2 envelope checks

Record environment (kernel, Docker, Compose versions) and aggregate redacted timings only.
