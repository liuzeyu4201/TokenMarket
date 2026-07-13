# Contract: Environment Mode Selection

**Version**: 1.0.0

**Applies to**: `migrate` and all future deployment-related commands

## Grammar

```text
mode := "local" | "test" | "prod"
```

Values are case-sensitive. Empty strings, whitespace variants, `dev`, `development`, `production`, and any unknown value are invalid.

## Selection rules

| Input | Effective result |
|-------|------------------|
| No `mode` argument | `local` |
| Make command line `mode=local` | `local` |
| Make command line `mode=test` | `test` |
| Make command line `mode=prod` | `prod`, pending independent approval |
| Shell/environment `mode=test|prod` without command-line origin | Ignore as escalation; effective `local` or fail safe if ambiguous |
| `.env`, filename, URL, `ENV`, `MODE` or other legacy signal | Never changes effective mode |
| Invalid/empty/mixed-case command-line value | `INVALID_MODE`, no resource access |

The implementation checks the Make variable origin or an equivalent explicit invocation marker. It must not use a simple default expression that accepts shell-injected `mode` for non-local environments.

## Configuration mapping

Mode is validated before choosing or reading a real configuration reference. Real files remain ignored by Git. The committed `.env.example` contains only names, comments and unusable synthetic placeholders.

The workflow must not copy `.env.test` or `.env.prod` to a generic `.env`, log resolved connection URLs, or infer mode from an existing file.

## Production approval

`prod` requires both:

1. Explicit command-line `mode=prod`.
2. A separate approval:
   - Interactive TTY: user types the exact documented production confirmation phrase.
   - Non-interactive: protected-environment approval proof bound to action, commit SHA and run ID.

Missing, expired, mismatched or unbound proof produces `PROD_APPROVAL_REQUIRED`. Rejection occurs before reading production secrets, resolving DNS, probing a host, opening a socket, starting a container or modifying data. Logs store only a safe approval reference.

## Deployment boundary

SF01 defines and tests this selector for future deployment scripts but does not implement cloud or production deployment. Future scripts must reuse this contract; they may not add an alternate `env`, `stage` or branch-inference selector.

## Recovery

An invalid selection has no side effects and may be retried with an explicit valid value. A failed production approval is not cached. A migration that starts after valid selection follows the reviewed owner backout runbook; changing mode during a run is forbidden.
