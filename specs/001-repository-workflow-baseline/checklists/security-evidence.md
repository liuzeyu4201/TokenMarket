# Security Evidence

**Feature**: `specs/001-repository-workflow-baseline/`  
**Date**: 2026-07-14

## Secret scan

```bash
gitleaks detect -s .
```

- Result: **PASSED** (exit 0)
- Scanned 4 commits, ~1.90 MB.
- No leaks found.
- Synthetic positive fixture is detected in the dedicated US2 test
  (`tests/workflow/test_secret_scan.py`) and its value is redacted in output.

## Dependency scans

### Go

```bash
govulncheck -C services/proxy-gateway ./...
```

- Result: **PASSED** (exit 0)
- No vulnerabilities found in called code.

### Python

```bash
uv export --project services/api-service --no-hashes > /tmp/api-reqs.txt
uv run --project tools/workflow pip-audit -r /tmp/api-reqs.txt --disable-pip --no-deps
```

- Result: **FAILED** (exit 1)
- Known vulnerabilities in `starlette 0.45.3`:
  - PYSEC-2026-161 → fix 1.0.1
  - PYSEC-2026-249 → fix 1.3.1
  - PYSEC-2026-248 → fix 1.3.0
  - PYSEC-2026-1942 → fix 0.49.1
  - PYSEC-2026-1941 → fix 0.47.2
  - PYSEC-2026-2281 → fix 1.1.0
  - PYSEC-2026-2280 → fix 1.1.0
- This finding blocks `make security-check` and therefore `make ci` until a
  reviewed dependency update or an approved, expiring exception is recorded.

### npm

```bash
npm audit --audit-level=moderate
```

- Result: **PASSED** (exit 0)
- Found 0 vulnerabilities.

## Image scan

```bash
make image-scan
```

- Result: **FAILED** (exit 2)
- Reason: Trivy 0.61.0 is not installed on the local workstation.
- The CLI returns `TOOL_MISSING` and fails closed rather than skipping the scan.

## Summary

| Scanner | Result | Notes |
|---------|--------|-------|
| gitleaks | PASSED | no leaks |
| govulncheck | PASSED | no called vulnerabilities |
| pip-audit | FAILED | starlette 0.45.3 known findings |
| npm audit | PASSED | no findings |
| trivy image | FAILED | tool not installed locally |

No unapproved HIGH/CRITICAL image findings exist because the image scan could
not run. The only approved blocker is the documented `starlette` dependency
finding, which requires a fix or formal exception before merge.
