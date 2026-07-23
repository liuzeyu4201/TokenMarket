# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

**Affected Components**: [gateway/services/frontend/shared contracts/infrastructure]

**Contracts**: [OpenAPI/event schema changes, compatibility strategy, or N/A]

**Data & Migrations**: [source of truth, transaction/idempotency model, migration and backout, or N/A]

**Security & Privacy**: [assets, trust boundaries, authorization, secret/PII handling, abuse cases]

**Observability & Reliability**: [SLIs/SLOs, logs/metrics/traces, alerts, timeouts/retries/degradation]

**Deployment & Rollback**: [artifact/config order, rollout checks, rollback decision and procedure]

## Constitution Check

*GATE: MUST pass before Phase 0 research and MUST be re-checked after Phase 1 design.*

- **Architecture and ownership**: Affected services and owners are explicit; no service reaches
  into another service's storage or implementation; each new component/dependency has an ADR.
- **Contracts and compatibility**: HTTP/event schemas, versioning, idempotency, timeout/retry,
  ordering, and deprecation behavior are defined before consumers are implemented.
- **Security and privacy**: Authentication/authorization, validation, secret/PII handling,
  threat cases, audit events, and required scans have concrete verification evidence.
- **Data correctness**: Source of truth, constraints, exact value representation, transaction
  boundaries, concurrency, migrations, reconciliation, backup/restore, and deletion are covered.
- **Testing**: Changed behavior has planned unit, contract, integration, negative, migration,
  and performance/recovery tests appropriate to its risk; tests precede implementation.
- **Operations**: Correlated redacted telemetry, health/readiness, SLIs/SLOs, alerts, runbooks,
  capacity/backpressure, and failure recovery are defined for new failure modes.
- **Delivery**: Reproducible toolchains, CI gates, dependency impact, rollout, rollback, and
  requirement-to-test traceability are documented.
- **Documentation language**: Project-authored Spec, Plan, Tasks, Checklist, ADR, runbook,
  handoff report, and development guidance default to Simplified Chinese; hand-written
  explanatory comments default to Simplified Chinese and explain intent/constraints rather
  than syntax; identifiers, API fields, CLI commands, paths, env vars, protocols, standards,
  library names, and proper nouns stay in original form; generated/third-party/license/
  external-contract/machine-consumed files need not be translated; unreviewed bulk translation
  of historical English is not required; new or substantially revised parts of existing
  English docs must follow this rule.

Any failed gate MUST block implementation or be recorded below with a linked ADR, accountable
owner, risk controls, review/expiry date, and remediation task. “MVP” or schedule pressure is
not a justification.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Keep the TokenMarket ownership boundaries below, remove unaffected
  entries, and expand affected entries with real paths for this feature.
-->

```text
services/
├── proxy-gateway/       # Go ingress, routing, forwarding, metering
├── api-service/         # Python application domains
├── billing-service/     # Python metering, ledger, settlement, reconciliation
└── admin-service/       # Python administrative API and authorization boundary
frontend/
├── src/                 # React application and generated/schema-checked API client
└── tests/
shared/
├── models/              # Versioned cross-language contract models
├── constants/           # Owned shared enums and error codes
└── utils/               # Only proven cross-component utilities
infra/                   # Docker, ingress, Kafka, and dashboard configuration
ops/                     # Migrations, alert rules, runbooks, and backup/restore assets
docs/
├── api/                 # OpenAPI and public integration documentation
└── decisions/           # Architecture Decision Records
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected | ADR / Owner | Controls | Review or Expiry |
|-----------|------------|-----------------------------|-------------|----------|------------------|
| [specific rule] | [concrete necessity] | [evidence] | [link / owner] | [risk reduction] | [YYYY-MM-DD] |
