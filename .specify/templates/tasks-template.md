---

description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are REQUIRED for every behavior change and MUST be written before implementation.
Documentation-only or non-behavioral mechanical changes may omit new tests only when the task list
records why no executable behavior changes.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **TokenMarket monorepo**: `services/proxy-gateway/`, `services/api-service/`,
  `services/billing-service/`, `services/admin-service/`, `frontend/`, `shared/`, `infra/`, `ops/`
- Tests live beside each component's established test root. Generated tasks MUST use the exact
  repository paths selected in plan.md rather than generic `src/` or `backend/` placeholders.

<!--
  ============================================================================
  IMPORTANT: The tasks below are SAMPLE TASKS for illustration purposes only.

  The /speckit-tasks command MUST replace these with actual tasks based on:
  - User stories from spec.md (with their priorities P1, P2, P3...)
  - Feature requirements from plan.md
  - Entities from data-model.md
  - Endpoints from contracts/

  Tasks MUST be organized by user story so each story can be:
  - Implemented independently
  - Tested independently
  - Delivered as an MVP increment

  DO NOT keep these sample tasks in the generated tasks.md file.
  ============================================================================
-->

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create project structure per implementation plan
- [ ] T002 Initialize [language] project with [framework] dependencies
- [ ] T003 [P] Configure linting and formatting tools
- [ ] T004 [P] Pin toolchains and dependencies with committed lockfiles
- [ ] T005 [P] Configure CI gates for format, lint, type checks, tests, scans, and builds

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

Examples of foundational tasks (adjust based on your project):

- [ ] T006 Define or update OpenAPI and event schemas with compatibility checks
- [ ] T007 Setup database schema, constraints, and reviewed migration/backout framework
- [ ] T008 [P] Implement authentication, server-side authorization, and audit framework
- [ ] T009 [P] Setup API routing, validation, idempotency, and error handling
- [ ] T010 Define transaction, outbox/inbox, reconciliation, and recovery mechanisms as applicable
- [ ] T011 [P] Configure structured redacted logs, correlation IDs, metrics, health/readiness, and alerts
- [ ] T012 Setup validated environment configuration and secret management
- [ ] T013 Establish integration-test dependencies and deterministic test-data factories

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - [Title] (Priority: P1) 🎯 MVP

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 1 (REQUIRED) ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T014 [P] [US1] Unit tests for [domain rules/error paths] in [exact test path]
- [ ] T015 [P] [US1] Contract tests for [HTTP/event schema] in [exact test path]
- [ ] T016 [P] [US1] Integration test for [user journey] in [exact test path]
- [ ] T017 [P] [US1] Negative tests for authorization, replay/concurrency, and failure recovery

### Implementation for User Story 1

- [ ] T018 [P] [US1] Create [Entity1] model in [exact source path]
- [ ] T019 [P] [US1] Create [Entity2] model in [exact source path]
- [ ] T020 [US1] Implement [Service] in [exact source path] (depends on T018, T019)
- [ ] T021 [US1] Implement [endpoint/feature] in [exact source path]
- [ ] T022 [US1] Add validation, authorization, idempotency, and safe error handling
- [ ] T023 [US1] Add correlated redacted telemetry, metrics, and operational alerts
- [ ] T024 [US1] Validate migration forward/backout and rollout/rollback where applicable

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 2 (REQUIRED) ⚠️

- [ ] T025 [P] [US2] Unit tests for [domain rules/error paths] in [exact test path]
- [ ] T026 [P] [US2] Contract tests for [HTTP/event schema] in [exact test path]
- [ ] T027 [P] [US2] Integration test for [user journey] in [exact test path]
- [ ] T028 [P] [US2] Negative tests for authorization, replay/concurrency, and failure recovery

### Implementation for User Story 2

- [ ] T029 [P] [US2] Create [Entity] model in [exact source path]
- [ ] T030 [US2] Implement [Service] in [exact source path]
- [ ] T031 [US2] Implement [endpoint/feature] in [exact source path]
- [ ] T032 [US2] Integrate with User Story 1 through its declared contract (if needed)
- [ ] T033 [US2] Add validation, authorization, idempotency, and safe error handling
- [ ] T034 [US2] Add telemetry and validate migration/rollout/rollback where applicable

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - [Title] (Priority: P3)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 3 (REQUIRED) ⚠️

- [ ] T035 [P] [US3] Unit tests for [domain rules/error paths] in [exact test path]
- [ ] T036 [P] [US3] Contract tests for [HTTP/event schema] in [exact test path]
- [ ] T037 [P] [US3] Integration test for [user journey] in [exact test path]
- [ ] T038 [P] [US3] Negative tests for authorization, replay/concurrency, and failure recovery

### Implementation for User Story 3

- [ ] T039 [P] [US3] Create [Entity] model in [exact source path]
- [ ] T040 [US3] Implement [Service] in [exact source path]
- [ ] T041 [US3] Implement [endpoint/feature] in [exact source path]
- [ ] T042 [US3] Integrate with prior stories through declared contracts (if needed)
- [ ] T043 [US3] Add validation, authorization, idempotency, and safe error handling
- [ ] T044 [US3] Add telemetry and validate migration/rollout/rollback where applicable

**Checkpoint**: All user stories should now be independently functional

---

[Add more user story phases as needed, following the same pattern]

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] TXXX [P] Documentation updates in docs/
- [ ] TXXX Code cleanup and refactoring
- [ ] TXXX Performance optimization across all stories
- [ ] TXXX [P] Additional risk-based unit, contract, integration, and recovery tests
- [ ] TXXX Run secret, dependency, container, and authorization security checks
- [ ] TXXX Validate dashboards, alerts, runbooks, and rollback procedure
- [ ] TXXX Run quickstart.md validation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - May integrate with US1 but should be independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - May integrate with US1/US2 but should be independently testable

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Models within a story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Contract test for [endpoint] in tests/contract/test_[name].py"
Task: "Integration test for [user journey] in tests/integration/test_[name].py"

# Launch all models for User Story 1 together:
Task: "Create [Entity1] model in [exact source path]"
Task: "Create [Entity2] model in [exact source path]"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
