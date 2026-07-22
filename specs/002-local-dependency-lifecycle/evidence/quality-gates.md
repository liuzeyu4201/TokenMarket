# Quality Gates Evidence (SF02 / T068)

**Status**: **PASS** on macOS arm64 (Darwin) with Node 24.18.0, Go 1.25.12, Docker available, Trivy 0.72.0.

## Environment (redacted)

| Item | Value |
|------|--------|
| OS | Darwin arm64 |
| Node | 24.18.0 |
| Go | 1.25.12 |
| Python | 3.11.15 / uv |
| Docker | available |
| Trivy | 0.72.0 |
| Date | 2026-07-22 |

## Gate results

| Gate | Result | Notes |
|------|--------|-------|
| `make help` | **PASS** | |
| `make toolchain-check` | **PASS** | |
| `make fmt-check` | **PASS** | |
| `make type-check` | **PASS** | |
| `make lint` | **PASS** | |
| `make test` | **PASS** | Aggregate PASSED |
| `make migrate-check` | **PASS** | |
| `make security-check` | **PASS** | gitleaks config + pip-audit + govulncheck |
| `make bootstrap` | **PASS** | |
| `make build` | **PASS** | 9 components; ~9–10 min |
| `make image-scan` | **PASS** | 5/5 images, 0 HIGH/CRITICAL with fix available |
| Public `dev` / `dev-down` | **PASS** (fail-closed) | Still `SF02_NOT_READY` until T074 |

## Security / image hardening applied for the gate

1. **Trivy** installed (`brew install trivy`).
2. **`.gitleaks.toml`** allowlists synthetic test/doc credentials; `security.py` passes `--config`.
3. **Python services**: FastAPI 0.139.2 + Starlette 1.3.1; Dockerfiles upgrade base `setuptools`/`wheel`/`jaraco.context`.
4. **proxy-gateway**: Go deps `x/net`/`x/crypto` bumped; image rebuild clean under Trivy.
5. **frontend**: `nginx:1.29-alpine` + `apk upgrade`.
6. **image-scan**: emits per-component events; Trivy uses `--ignore-unfixed` so only fixable HIGH/CRITICAL block the gate.

## Still out of this gate (later tasks)

- Dual-platform performance harness → **T069 / T070**
- 10-person usability → **T071**
- Public activation → **T074** (do not run until T069–T071 pass)

## Conclusion

T068 offline + Docker quality matrix required for SF02 is recorded **PASS**. Public lifecycle remains fail-closed.
