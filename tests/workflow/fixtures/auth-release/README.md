# Auth release fixtures (feature 004 / T091)

Synthetic, secret-free auth release candidate fixtures for
`tests/workflow/test_auth_deploy_gate.py`.

These fixtures must **not** reference or load the feature's real evidence
directory under `specs/` (tests assert fixtures stay self-contained).

| Directory | Intent |
|-----------|--------|
| `valid/` | Complete evidence bindings + approved activation |
| `missing-evidence/` | Omits a required evidence key |
| `hash-mismatch/` | Companion `.sha256` does not match JSON bytes |
| `digest-mismatch/` | Invalid OCI digest form |
| `synthetic-prod/` | Valid structure but synthetic SMS / TLS not ready |

Regenerate companions with the helper in `test_auth_deploy_gate.py` if payloads change.
