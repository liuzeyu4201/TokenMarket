# US2 Security Evidence

**Feature**: specs/001-repository-workflow-baseline — 仓库工程工作流基线  
**Story**: US2 — 安全地准备本地配置  
**Recorded**: 2026-07-15  
**Environment**: macOS, Go 1.25.12, Python 3.11.15, Node 24.18.0, Docker Desktop

## 1. Git Ignore Rules

`.gitignore` rejects local configuration and secrets while allowing safe example
definitions:

```text
.env
.env.*
!.env.example
!.env.*.example
```

Verified by `tests/workflow/test_configuration.py`:

- `test_gitignore_rejects_env_files` PASSED
- `test_gitignore_allows_example_definitions` PASSED

## 2. `.env.example` Configuration Definition

Root `.env.example` declares SF01 variables with safe placeholders only:

| Variable | Purpose | Sensitive | Placeholder |
|----------|---------|-----------|-------------|
| `MODE` | operational mode | No | `local` |
| `DATABASE_URL` | PostgreSQL connection | Yes | `postgresql://app:replace-me@localhost:5432/tokenmarket` |
| `ADMIN_DATABASE_URL` | reserved admin DB URL | Yes | same safe placeholder |
| `REDIS_URL` | reserved for SF02 | No | `redis://localhost:6379/0` |
| `KAFKA_BROKERS` | reserved for SF02 | No | `localhost:9092` |
| `AI_GATEWAY_URL` | reserved for SF02 | No | `https://api.example.local` |
| `AI_GATEWAY_KEY` | reserved for SF02 | Yes | `sk-replace-me` |

No real addresses, passwords or provider keys are present.

## 3. Configuration Preflight

`tools/workflow/security.py::validate_config` rejects missing, empty, wrongly-typed
and dangerous-default values before any persistent side effect. Error messages
expose only variable names.

Test evidence (`tests/workflow/test_config_preflight.py`):

- `test_missing_required_variable_fails` PASSED
- `test_empty_required_variable_fails` PASSED
- `test_wrong_type_variable_fails` PASSED
- `test_dangerous_production_default_fails` PASSED
- `test_valid_local_config_passes` PASSED

## 4. Redaction

`tools/workflow/security.py::redact` removes secret-like values while preserving
variable names. Patterns cover:

- `sk-*` API keys
- `api_key`, `secret`, `token`, `password` assignments
- `Bearer` tokens

Test evidence (`tests/workflow/test_redaction.py`): **9 passed, 0 failed**.

## 5. Secret Scan

`make security-check` invokes `gitleaks detect` over the full Git history. A
synthetic fixture test (`tests/workflow/test_secret_scan.py`) is skipped on hosts
without `gitleaks` installed; on this host `gitleaks` 8.24.0 is available and the
scan runs.

## 6. Dependency Scans

`make security-check` runs:

- `govulncheck` on `services/proxy-gateway`
- `pip-audit` on exported `services/api-service` requirements
- `npm audit --audit-level=moderate` in `frontend`

Installed scanner versions:

| Scanner | Version |
|---------|---------|
| gitleaks | 8.24.0 |
| govulncheck | 1.1.4 |
| pip-audit | 2.10.1 |
| npm audit | 11.16.0 |

### Known Finding

`pip-audit` reports known vulnerabilities in `starlette 0.45.3` (a transitive
dependency of FastAPI 0.115.8). Example advisory: `PYSEC-2026-161`. The scan
fails closed as required; remediation is tracked for a follow-up dependency bump
and is outside the SF01 scope of preparing the scanning gate itself.

## 7. Dockerfile Build-Hygiene

All five Dockerfiles:

- Do not accept secret build arguments.
- Do not copy `.env*` files into images.
- Run services as non-root users.
- Do not leave sensitive build-layer artifacts behind.

## 8. Runbook

`ops/runbooks/workflow.md` documents:

- Local configuration workflow: copy `.env.example` → `.env.local`.
- Secret discovery response: revoke/rotate, audit, open tracked issue.
- Exception format with owner, approver, issue and expiry fields.

## 9. Sign-off

US2 implementation provides safe local configuration preparation, secret
redaction, fail-closed security scanning, and documented exception handling. The
single open dependency finding demonstrates the scanner is functioning and will
be remediated through the normal dependency-update workflow.
