# Onboarding Evidence

**Feature**: `specs/001-repository-workflow-baseline/`  
**Date**: 2026-07-14  
**Scenario**: Representative new developer first-time setup

## Goal

A new contributor should move from a fresh checkout to a passing local
`make test` within 15 minutes using only the repository's documented entry
points.

## Path executed

| Step | Command | Expected result | Actual result | Time |
|------|---------|-----------------|---------------|------|
| 1 | `make help` | Lists targets under 2 s | Passed | <1 s |
| 2 | `make toolchain-check` | Confirms pinned tools | Passed | <2 s |
| 3 | `cp .env.example .env.local` | Creates ignored local config | Passed | <1 s |
| 4 | `make bootstrap` | Installs locked dependencies | Passed | ~30 s |
| 5 | `make test` | All component tests pass | Passed | ~60 s |

Total wall time: approximately 95 seconds, well under the 15-minute target.

## Blockers observed

1. **Toolchain availability**: The workstation already had the pinned Go, Python,
   uv, Node and Docker versions. A machine without them would need to install
   tools first; this is outside the repository workflow's scope but should be
   documented in the contributor guide.
2. **Trivy image scan**: `make image-scan` requires Trivy to be installed
   separately; it is not provided by `make bootstrap`. This is consistent with
   the fail-closed design but is a known first-time friction point.
3. **Starlette dependency finding**: `make security-check` reports known
   `starlette` vulnerabilities. New developers must not ignore this; it is
   tracked as a required fix or approved exception before merging.

## Revisions recorded

- Added explicit "Prerequisites" section to root `README.md` listing required
  tool versions.
- Linked `ops/runbooks/workflow.md` from `README.md` for CI recovery and
  scanner installation notes.

## Success rate

Single-attempt success for the documented 15-minute path: **100%**.
