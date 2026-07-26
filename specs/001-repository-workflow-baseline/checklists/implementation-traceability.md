# 实现可追溯性

**功能**：`specs/001-repository-workflow-baseline/`
**日期**：2026-07-14

本清单验证 `spec.md` 中的每一项功能需求（FR）、工程需求（ER）
与安全/控制需求（SC）均有对应的实现任务与测试证据。映射最初在
`tasks.md` 中建立，并在实现后于此处校验。

## 功能需求

| 需求 | 主要任务 | 测试 / 证据文件 |
|-------------|---------------|------------------------|
| FR-001 | T012, T069, T073, T075, T082 | `ops/workflow/components.json`, `tests/workflow/test_component_manifest.py`, `tests/workflow/test_structure.py`, 组件 README |
| FR-002 | T012, T069, T071, T073, T075, T080 | `tests/workflow/test_boundaries.py`, `.github/CODEOWNERS` |
| FR-003 | T015, T033, T035, T038, T042, T046, T049, T055 | 根 `Makefile`、组件 Makefile、`tests/workflow/test_command_contract.py` |
| FR-004 | T015, T033, T087, T097 | `tests/workflow/test_accessibility_performance.py`, `README.md` |
| FR-005 | T015–T017, T031–T033, T055 | `tools/workflow/events.py`, `tools/workflow/cli.py`, `tests/workflow/test_events.py` |
| FR-006 | T016, T021–T055 | 组件健康测试、`tests/workflow/test_component_manifest.py` |
| FR-007 | T018, T032, T033 | `tests/workflow/test_toolchains.py`, `tools/workflow/cli.py` |
| FR-008 | T019, T033, T055 | `tests/workflow/test_sf02_transition.py` |
| FR-009 | T015, T019, T033 | 根 `Makefile`、`tests/workflow/test_sf02_transition.py` |
| FR-010 | T016, T033, T035, T038, T042, T046, T049, T051–T053 | 组件 Makefile、资产校验器 |
| FR-011 | T015, T035, T038, T042, T046, T049, T075, T094 | `tests/workflow/test_command_contract.py`、根 `Makefile` |
| FR-012 | T084, T093, T104 | `tests/workflow/test_dirty_format.py`、组件 `fmt-check` 目标 |
| FR-013 | T029, T036, T040, T044, T047, T050–T053, T089, T108 | `tests/workflow/test_images.py`、Dockerfile、`tests/workflow/test_reproducibility.py` |
| FR-014 | T014, T020, T039, T043, T054, T085, T090, T091, T094, T095 | `ops/migrations/owners.json`、Alembic 迁移、`tests/workflow/test_mode.py`、`.github/workflows/ci.yml` |
| FR-015 | T056, T061 | `tests/workflow/test_configuration.py`, `.env.example` |
| FR-016 | T056, T062, T068 | `tests/workflow/test_configuration.py`, `.gitignore` |
| FR-017 | T058, T059, T063–T066, T106 | `tools/workflow/security.py`, `tests/workflow/test_redaction.py`, `tests/workflow/test_secret_scan.py` |
| FR-018 | T001–T008, T013, T018, T033, T060, T095 | `.tool-versions`, `ops/workflow/toolchains.json`, `.github/workflows/ci.yml` |
| FR-019 | T010–T012, T026, T070, T074, T076, T079 | `shared/contracts/`, `tests/workflow/test_contracts.py`, `docs/api/README.md` |
| FR-020 | T073, T097, T105 | 组件 README、根 `README.md`、入门证据 |
| FR-021 | T012, T031–T033, T072, T075 | `tools/workflow/manifest.py`, `tests/workflow/test_adr_policy.py` |
| FR-022 | T083, T092, T100 | `tests/workflow/test_paths.py`, `tools/workflow/cli.py` |
| FR-023 | T084, T086, T093, T100 | `tests/workflow/test_dirty_format.py`, `tests/workflow/test_retry_safety.py` |
| FR-024 | T009, T072, T081, T107 | `docs/decisions/001-github-actions-ci-adapter.md`, `docs/decisions/README.md` |
| FR-025 | T020, T088, T094–T100, T108 | `.github/workflows/ci.yml`、`tests/workflow/test_ci_contract.py`、根 `Makefile` |
| FR-026 | T020, T054, T085, T090, T091, T100 | `tools/workflow/mode.py`、`tests/workflow/test_mode.py`、迁移检查 |

## 工程需求

| 需求 | 主要任务 | 测试 / 证据文件 |
|-------------|---------------|------------------------|
| ER-001 | T010, T015, T033, T070, T076, T088, T101 | `shared/contracts/`、`.github/workflows/ci.yml`、链接校验 |
| ER-002 | T056–T068, T106 | `tools/workflow/security.py`, `tests/workflow/test_redaction.py` |
| ER-003 | T014, T020, T039, T043, T054, T094, T095 | `ops/migrations/owners.json`、Alembic 迁移、CI 工作流 |
| ER-004 | T018, T087, T104 | `tests/workflow/test_toolchains.py`, `tests/workflow/test_accessibility_performance.py` |
| ER-005 | T017, T084, T086, T089, T104, T108 | `tests/workflow/test_dirty_format.py`, `tests/workflow/test_retry_safety.py`, `tests/workflow/test_reproducibility.py` |
| ER-006 | T017, T021–T024, T030, T055 | `tools/workflow/events.py`、组件健康测试 |
| ER-007 | T025, T087, T097 | `frontend/src/App.test.tsx`, `tests/workflow/test_accessibility_performance.py`, `README.md` |

## 安全/控制需求

| 需求 | 主要任务 | 测试 / 证据文件 |
|-------------|---------------|------------------------|
| SC-001 | T087, T097, T105 | 可访问性/入门证据 |
| SC-002 | T015–T018, T032, T033, T055, T057 | `tools/workflow/events.py`、脱敏测试、配置预检 |
| SC-003 | T084, T086, T089, T104, T108 | 可复现性与重试测试 |
| SC-004 | T020, T088, T094, T095, T099, T100, T108 | CI 工作流、规则集运行手册 |
| SC-005 | T056–T068, T106 | 安全扫描证据 |
| SC-006 | T069–T076, T082 | 结构、契约与边界测试 |
| SC-007 | T083, T087, T092, T100 | 路径与可访问性测试 |
| SC-008 | T015, T019, T033, T084, T093 | 脏格式化与 fmt-check 测试 |
| SC-009 | T016, T021–T055, T108 | 组件健康与最终 CI 证据 |
| SC-010 | T084, T093, T100, T104 | 幂等格式化与可复现性 |
| SC-011 | T020, T054, T085, T090, T091, T100 | 模式与迁移批准测试 |
| SC-012 | T019, T033, T055 | SF02 过渡测试 |

## 校验结果

FR-001 至 FR-026、ER-001 至 ER-007 以及 SC-001 至 SC-012
均至少有一项已合并任务与一项测试或证据产物。实现期间
未新增、删除或重新编号任何需求。
