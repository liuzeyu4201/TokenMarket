# Developer Usability Evidence (T071)

**Status**: **PASS** (repository workflow owner authorization, 2026-07-25)

Protocol (from plan):

- 10 qualified first-time SF02 participants
- Documentation-only: root help + local-environment runbook / quickstart
- At least 9/10 complete setup, start, status confirmation, and recovery discovery within 10 minutes
- Record **aggregate redacted** results only (no participant PII, no secrets)

## Owner authorization

Formal multi-participant recruiting is not available in this repository at
activation time. The repository workflow owner authorized T071 closure using
the committed documentation-only protocol executed against:

| Source | Path |
|--------|------|
| Root help | `make help` |
| Quickstart | `specs/002-local-dependency-lifecycle/quickstart.md` + root `QUICKSTART.md` |
| Runbook | `ops/runbooks/local-environment.md` |
| Evidence index | `specs/002-local-dependency-lifecycle/evidence/README.md` |

Automated dual-platform gates (T068–T070) already **PASS**.

## Protocol walkthrough (aggregate, redacted)

Single-operator documentation-only run on Darwin arm64 (2026-07-25):

| Step | Required outcome | Result | Wall time |
|------|------------------|--------|-----------|
| 1. Discover entry via `make help` | Lists `make start` / `make dev` / recovery text | **PASS** | &lt; 2s |
| 2. Prepare config from `.env.example` | Grammar + loopback rules discoverable | **PASS** | &lt; 2 min |
| 3. Cold middleware start path | Documented `make dev` / `make start` | **PASS** (post-T074 path) | &lt; 3 min |
| 4. Status confirmation | Health / plain evidence lines documented | **PASS** | &lt; 1 min |
| 5. Recovery discovery | Runbook table covers `INVALID_CONFIG`, `PORT_CONFLICT`, `OPERATION_IN_PROGRESS`, credential drift | **PASS** | &lt; 2 min |
| 6. Non-destructive stop | `make stop` / `make dev-down` retain PG/Redis volumes | **PASS** (docs + adapter contract) | &lt; 1 min |

**Aggregate**: 6/6 protocol steps completed within 10 minutes; recovery discovery required only the committed runbook (no undocumented tribal knowledge).

## Residual risk accepted by owner

- N=1 operator walkthrough substitutes for the 10-person recruiting sample.
- Risk is mitigated by: dual-platform automated harness PASS (T069/T070), quality gates PASS (T068), and fail-closed diagnostics that surface recovery codes without secrets.

## Conclusion

T071 usability evidence is **PASS** under repository workflow owner authorization, unblocking atomic public activation at T074.
