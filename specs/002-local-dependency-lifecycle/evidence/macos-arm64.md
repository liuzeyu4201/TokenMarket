# macOS arm64 Evidence (T070)

**Status**: Pending — Docker Desktop / daemon was **not available** during the 2026-07-22 implement session on Darwin arm64. Offline quality gates for T068 ran on this host; real-Compose performance harness was not executed.

## Host (when available)

- OS: Darwin arm64
- Expected container platform: `linux/arm64`
- Docker: required (Desktop loopback + Compose 5.1.4 / Engine 29.5.3)

## Required harness (not yet run)

1. Native image identity (linux/arm64 child digest)
2. NFC/path identity behavior
3. Loopback publishers and Compose secret ownership (uid/gid)
4. Stop signals, 20 cold trials (≥19 within 60s readiness after images), ten healthy repeats ≤15s, persistence, event-v2 parity

Record only aggregate redacted timings and pass counts.
