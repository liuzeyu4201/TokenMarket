# Implementation Traceability

**Feature**: `specs/001-repository-workflow-baseline/`  
**Date**: 2026-07-14

This checklist verifies that every functional requirement (FR), engineering
requirement (ER) and security/control requirement (SC) from `spec.md` has a
corresponding implementation task and test evidence. The mapping was first
established in `tasks.md` and is validated here after implementation.

## Functional Requirements

| Requirement | Primary tasks | Test / evidence files |
|-------------|---------------|------------------------|
| FR-001 | T012, T069, T073, T075, T082 | `ops/workflow/components.json`, `tests/workflow/test_component_manifest.py`, `tests/workflow/test_structure.py`, component READMEs |
| FR-002 | T012, T069, T071, T073, T075, T080 | `tests/workflow/test_boundaries.py`, `.github/CODEOWNERS` |
| FR-003 | T015, T033, T035, T038, T042, T046, T049, T055 | Root `Makefile`, component Makefiles, `tests/workflow/test_command_contract.py` |
| FR-004 | T015, T033, T087, T097 | `tests/workflow/test_accessibility_performance.py`, `README.md` |
| FR-005 | T015–T017, T031–T033, T055 | `tools/workflow/events.py`, `tools/workflow/cli.py`, `tests/workflow/test_events.py` |
| FR-006 | T016, T021–T055 | Component health tests, `tests/workflow/test_component_manifest.py` |
| FR-007 | T018, T032, T033 | `tests/workflow/test_toolchains.py`, `tools/workflow/cli.py` |
| FR-008 | T019, T033, T055 | `tests/workflow/test_sf02_transition.py` |
| FR-009 | T015, T019, T033 | Root `Makefile`, `tests/workflow/test_sf02_transition.py` |
| FR-010 | T016, T033, T035, T038, T042, T046, T049, T051–T053 | Component Makefiles, asset validators |
| FR-011 | T015, T035, T038, T042, T046, T049, T075, T094 | `tests/workflow/test_command_contract.py`, root `Makefile` |
| FR-012 | T084, T093, T104 | `tests/workflow/test_dirty_format.py`, component `fmt-check` targets |
| FR-013 | T029, T036, T040, T044, T047, T050–T053, T089, T108 | `tests/workflow/test_images.py`, Dockerfiles, `tests/workflow/test_reproducibility.py` |
| FR-014 | T014, T020, T039, T043, T054, T085, T090, T091, T094, T095 | `ops/migrations/owners.json`, Alembic migrations, `tests/workflow/test_mode.py`, `.github/workflows/ci.yml` |
| FR-015 | T056, T061 | `tests/workflow/test_configuration.py`, `.env.example` |
| FR-016 | T056, T062, T068 | `tests/workflow/test_configuration.py`, `.gitignore` |
| FR-017 | T058, T059, T063–T066, T106 | `tools/workflow/security.py`, `tests/workflow/test_redaction.py`, `tests/workflow/test_secret_scan.py` |
| FR-018 | T001–T008, T013, T018, T033, T060, T095 | `.tool-versions`, `ops/workflow/toolchains.json`, `.github/workflows/ci.yml` |
| FR-019 | T010–T012, T026, T070, T074, T076, T079 | `shared/contracts/`, `tests/workflow/test_contracts.py`, `docs/api/README.md` |
| FR-020 | T073, T097, T105 | Component READMEs, root `README.md`, onboarding evidence |
| FR-021 | T012, T031–T033, T072, T075 | `tools/workflow/manifest.py`, `tests/workflow/test_adr_policy.py` |
| FR-022 | T083, T092, T100 | `tests/workflow/test_paths.py`, `tools/workflow/cli.py` |
| FR-023 | T084, T086, T093, T100 | `tests/workflow/test_dirty_format.py`, `tests/workflow/test_retry_safety.py` |
| FR-024 | T009, T072, T081, T107 | `docs/decisions/001-github-actions-ci-adapter.md`, `docs/decisions/README.md` |
| FR-025 | T020, T088, T094–T100, T108 | `.github/workflows/ci.yml`, `tests/workflow/test_ci_contract.py`, root `Makefile` |
| FR-026 | T020, T054, T085, T090, T091, T100 | `tools/workflow/mode.py`, `tests/workflow/test_mode.py`, migration checks |

## Engineering Requirements

| Requirement | Primary tasks | Test / evidence files |
|-------------|---------------|------------------------|
| ER-001 | T010, T015, T033, T070, T076, T088, T101 | `shared/contracts/`, `.github/workflows/ci.yml`, link validation |
| ER-002 | T056–T068, T106 | `tools/workflow/security.py`, `tests/workflow/test_redaction.py` |
| ER-003 | T014, T020, T039, T043, T054, T094, T095 | `ops/migrations/owners.json`, Alembic migrations, CI workflow |
| ER-004 | T018, T087, T104 | `tests/workflow/test_toolchains.py`, `tests/workflow/test_accessibility_performance.py` |
| ER-005 | T017, T084, T086, T089, T104, T108 | `tests/workflow/test_dirty_format.py`, `tests/workflow/test_retry_safety.py`, `tests/workflow/test_reproducibility.py` |
| ER-006 | T017, T021–T024, T030, T055 | `tools/workflow/events.py`, component health tests |
| ER-007 | T025, T087, T097 | `frontend/src/App.test.tsx`, `tests/workflow/test_accessibility_performance.py`, `README.md` |

## Security/Control Requirements

| Requirement | Primary tasks | Test / evidence files |
|-------------|---------------|------------------------|
| SC-001 | T087, T097, T105 | Accessibility/onboarding evidence |
| SC-002 | T015–T018, T032, T033, T055, T057 | `tools/workflow/events.py`, redaction tests, config preflight |
| SC-003 | T084, T086, T089, T104, T108 | Reproducibility and retry tests |
| SC-004 | T020, T088, T094, T095, T099, T100, T108 | CI workflow, ruleset runbook |
| SC-005 | T056–T068, T106 | Security scans evidence |
| SC-006 | T069–T076, T082 | Structure, contract and boundary tests |
| SC-007 | T083, T087, T092, T100 | Path and accessibility tests |
| SC-008 | T015, T019, T033, T084, T093 | Dirty-format and fmt-check tests |
| SC-009 | T016, T021–T055, T108 | Component health and final CI evidence |
| SC-010 | T084, T093, T100, T104 | Idempotent format and reproducibility |
| SC-011 | T020, T054, T085, T090, T091, T100 | Mode and migration approval tests |
| SC-012 | T019, T033, T055 | SF02 transition tests |

## Validation result

All FR-001 through FR-026, ER-001 through ER-007, and SC-001 through SC-012
have at least one merged task and one test or evidence artifact. No requirement
was added, removed or renumbered during implementation.
