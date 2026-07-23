<!--
Sync Impact Report
- Version change: template (unratified) -> 1.0.0; 1.0.0 -> 1.1.0 (long-lived branches
  master/master-dev); 1.1.0 -> 1.2.0 (Chinese-first engineering documentation)
- Modified principles:
  - Placeholder Principle 1 -> I. Architecture Boundaries and Contract-First Design
  - Placeholder Principle 2 -> II. Secure by Default (NON-NEGOTIABLE)
  - Placeholder Principle 3 -> III. Data Correctness and Recoverability (NON-NEGOTIABLE)
  - Placeholder Principle 4 -> IV. Typed, Maintainable, and Minimal Code
  - Placeholder Principle 5 -> V. Test Evidence Before Merge (NON-NEGOTIABLE)
- Added principles:
  - VI. Observable and Reliable Operation
  - VII. Reproducible Delivery and Controlled Change
  - VIII. Chinese-First Engineering Documentation (1.2.0)
- Added sections:
  - Technology and Architecture Constraints
  - Development Workflow and Quality Gates
- Removed sections: none; template placeholders were concretized
- Templates requiring updates:
  - ✅ updated: .specify/templates/plan-template.md
  - ✅ updated: .specify/templates/spec-template.md
  - ✅ updated: .specify/templates/tasks-template.md
  - ✅ reviewed/no change: .specify/templates/checklist-template.md
  - ✅ reviewed/no change: .specify/templates/constitution-template.md
  - ✅ reviewed/no command templates present: .specify/templates/commands/*.md
- Runtime guidance reviewed:
  - ✅ aligned as technical references: 项目开发/1-项目架构与目录结构.md
  - ✅ aligned as technical references: 项目开发/2-Go代理网关开发规范.md
  - ✅ aligned as technical references: 项目开发/3-Python后端与数据库设计规范.md
  - ✅ aligned as technical references: 项目开发/4-前端与DevOps监控规范.md
  - ⚠ pending product decision: 项目开发/V0.1/V0.1_0712/V0.1_0712_功能开发Spec.md
    contains prototype plaintext credential clauses that this constitution forbids.
- Follow-up TODOs:
  - Amend the V0.1 feature spec before implementation; plaintext passwords and provider
    API keys are not eligible for a development-stage exception.
  - No bulk translation of existing English documents is required by v1.2.0; new and
    substantially revised project-authored content must follow Principle VIII.
-->

# TokenMarket Engineering Constitution

This constitution governs software architecture, code implementation, data engineering,
verification, operations, and delivery. It does not define product strategy, commercial rules,
feature scope, or business explanations; those belong in product specifications and MUST comply
with the engineering constraints established here.

## Core Principles

### I. Architecture Boundaries and Contract-First Design

- The repository MUST remain a monorepo with explicit ownership boundaries between the
  Go proxy gateway, Python domain services, React frontend, shared contracts, and
  infrastructure. A service MUST own its domain rules and persistence access; another
  service MUST NOT reach into its database or import its internal implementation.
- The Go gateway MUST remain the only ingress for proxied AI traffic and MUST limit its
  responsibilities to authentication, rate limiting, routing, forwarding, metering,
  health checks, and request-level telemetry. Domain workflows belong in the appropriate
  Python service; presentation and client state belong in the React frontend.
- HTTP APIs, Kafka events, and shared schemas MUST be designed and versioned before their
  consumers are implemented. OpenAPI or an equivalent machine-readable schema MUST define
  HTTP contracts; event schemas MUST define an event ID, type, version, timestamp, payload,
  producer, and correlation ID.
- Synchronous calls MUST use bounded timeouts and deliberate retry/circuit-breaker rules.
  Only proven-idempotent operations may be retried automatically. Asynchronous consumers
  MUST be idempotent, commit offsets only after durable processing, and route exhausted
  failures to a dead-letter path.
- A new service, datastore, protocol, shared abstraction, or cross-service dependency MUST
  be justified by an ADR. The ADR MUST state ownership, failure modes, operational cost,
  migration/rollback, and why the current design cannot meet the requirement.

Rationale: explicit boundaries and executable contracts keep independently deployable
components compatible without turning the monorepo into a distributed monolith.

### II. Secure by Default (NON-NEGOTIABLE)

- Secrets, passwords, access tokens, provider API keys, encryption keys, and personal or
  financial data MUST NOT be committed, logged, placed in fixtures, returned in errors, or
  stored in plaintext. Local and test environments MUST use synthetic credentials through
  ignored environment files or a secret provider. `.env.example` MUST contain names and
  safe placeholders only.
- Provider API keys and other reversible high-value secrets MUST use authenticated
  encryption at rest with externally supplied, versioned key material. Passwords MUST use
  a purpose-built adaptive password hash. Secret comparison, rotation, revocation, and
  redaction paths MUST be testable.
- Every external input and deserialized event MUST be schema-validated. Database access MUST
  use parameterized ORM/query APIs; rendered user content MUST be escaped by default; file,
  URL, and command inputs MUST be allowlisted where applicable.
- Authentication and authorization MUST be enforced server-side using least privilege and
  deny-by-default RBAC. Sensitive operations MUST require explicit authorization, audit
  records, and replay protection or step-up verification according to risk.
- Production traffic MUST use TLS; service authentication MUST be stronger than a shared
  static token before exposure outside an isolated development network. Security-relevant
  dependencies and container images MUST be scanned, and unresolved critical/high findings
  MUST block release unless an approved, time-bounded risk acceptance exists.
- Logs, traces, metrics, analytics, snapshots, and backups MUST follow the same data
  classification and redaction rules as primary storage. Test data MUST NOT be copied from
  production unless irreversibly anonymized and explicitly approved.

Rationale: TokenMarket handles third-party credentials and value-bearing records; a
prototype label does not reduce the impact of credential disclosure or unauthorized writes.

### III. Data Correctness and Recoverability (NON-NEGOTIABLE)

- PostgreSQL is the system of record for transactional state. Redis is an ephemeral cache,
  lock, session, or rate-limit store and MUST NOT be the sole copy of durable facts. Kafka
  transports events and MUST NOT substitute for an explicitly owned source of truth.
- Schema design MUST declare primary keys, foreign keys, nullability, uniqueness, check
  constraints, timestamps, and indexes from observed query patterns. Money, credits, quota,
  and token counts MUST use integer base units or exact fixed-precision decimals; binary
  floating point MUST NOT represent value-bearing amounts.
- Every state-changing API, event consumer, scheduled job, settlement, and external callback
  MUST define an idempotency key and duplicate behavior. Financial or quota mutations MUST
  be atomic, concurrency-safe, and accompanied by an immutable ledger/audit record; balances
  MUST be derivable or reconcilable from those records.
- Database changes MUST use reviewed Alembic migrations. Applied migrations MUST never be
  edited. Destructive or locking changes MUST use an expand-migrate-contract sequence with
  compatibility and rollback/backout instructions. Application startup MUST NOT silently
  mutate production schemas.
- Transaction boundaries MUST be explicit and short. Cross-service consistency MUST use an
  outbox/inbox, saga, or equally auditable pattern; distributed dual writes without recovery
  logic are forbidden.
- Backup, retention, restore, reconciliation, and data deletion procedures MUST be specified
  for each persistent dataset. A backup claim is incomplete until a restore test has passed
  in a non-production environment and its evidence is recorded.

Rationale: retries, concurrency, partial failure, and schema evolution are normal operating
conditions; correctness must be enforced by design rather than repaired manually.

### IV. Typed, Maintainable, and Minimal Code

- Go code MUST pass `gofmt`, `go vet`, and the repository's `golangci-lint` policy. Python
  code MUST use type annotations at service boundaries and pass the configured formatter,
  linter, and type checker. Frontend code MUST use TypeScript strict mode and MUST NOT use
  untyped escape hatches such as `any` without a localized justification.
- Dependencies MUST flow from transport and infrastructure adapters toward application and
  domain interfaces. Handlers/controllers MUST validate and translate; domain services MUST
  own rules; repositories MUST own persistence. Business decisions MUST NOT be duplicated in
  routes, React components, SQL snippets, or provider adapters.
- Public APIs and non-obvious algorithms MUST document invariants, failure behavior, and
  units. Names and types MUST carry meaning; comments MUST explain constraints or reasoning,
  not restate syntax.
- Implementations MUST prefer the simplest design that meets measured requirements. SOLID,
  DDD, repositories, factories, or shared packages MUST be applied only where they protect a
  real boundary or variation point. Premature microservices, generic frameworks, and copy-
  based shared models are forbidden without an ADR and an owner.
- Dependencies MUST be actively maintained, version constrained through committed lockfiles,
  license-compatible, and minimized. Generated code MUST be reproducible and MUST NOT be
  manually edited.

Rationale: strict types and narrow ownership catch integration defects early, while explicit
simplicity prevents mature practices from becoming unmaintainable ceremony.

### V. Test Evidence Before Merge (NON-NEGOTIABLE)

- Every behavior change MUST add or update an automated test that fails without the change.
  Documentation-only or non-behavioral mechanical changes may omit new tests, but the PR MUST
  state why no executable behavior changed.
- Domain rules, parsing, routing, metering, authorization, idempotency, and error mapping MUST
  have deterministic unit tests. HTTP and event schemas MUST have consumer/provider contract
  tests. Persistence, migrations, cache/queue integration, and critical user journeys MUST
  have integration tests against real version-compatible dependencies; repository-standard
  container orchestration is the default test environment.
- Credential handling, access control, duplicate/replay behavior, concurrent balance/quota
  updates, failure recovery, and migration forward/backout paths MUST include negative tests.
  Gateway hot paths and stated latency/throughput targets MUST include repeatable benchmarks
  or load tests with the environment and acceptance threshold recorded.
- Tests MUST be isolated, deterministic, and runnable through repository-standard commands.
  Flaky tests MUST be fixed or quarantined with an owner and expiry; they MUST NOT be retried
  until green and treated as evidence of correctness.
- Coverage is a diagnostic, not a substitute for assertions. Changed critical code MUST meet
  the repository threshold (initial baseline: 80% line coverage for Go and Python domain
  packages), and security/financial invariants MUST have direct branch coverage regardless of
  the aggregate percentage.

Rationale: review establishes intent; repeatable tests establish that contracts and failure
modes continue to hold as the system changes.

### VI. Observable and Reliable Operation

- Every request and event MUST carry a correlation/request ID across service boundaries.
  Services MUST emit structured logs with timestamp, severity, service, version, environment,
  operation/event, correlation ID, outcome, and safe diagnostic fields. Secret or personal
  data redaction MUST happen before serialization.
- Every deployable service MUST expose separate liveness and readiness signals, Prometheus-
  compatible metrics, and actionable error reporting. Critical paths MUST measure rate,
  errors, duration, and saturation; value-bearing flows MUST expose reconciliation lag and
  failure/dead-letter counts.
- A feature that creates a new failure mode MUST define detection, alert severity, ownership,
  runbook action, timeout/retry/degradation behavior, and recovery evidence before release.
  Alerts MUST map to a user or integrity impact and MUST NOT be based only on noisy symptoms.
- Performance and availability claims MUST be measurable in the target environment and tied
  to a stated SLI/SLO. Optimizations MUST include a before/after measurement and MUST preserve
  correctness. Capacity limits, backpressure, and graceful shutdown MUST be explicit for
  gateway workers, HTTP clients, database pools, and event consumers.

Rationale: distributed failures cannot be diagnosed or safely recovered without correlated,
redacted telemetry and pre-defined operating behavior.

### VII. Reproducible Delivery and Controlled Change

- Local, CI, test, and production builds MUST use the same version-constrained toolchains and
  committed dependency lockfiles. Containers MUST use multi-stage builds, minimal pinned base
  images, non-root runtime users, health checks, and immutable tags containing the semantic
  version and commit SHA.
- The repository MUST provide stable commands for bootstrap, format, lint, type-check, test,
  build, migrate, and local integration. CI MUST run the same commands and MUST block merge on
  formatting, static analysis, tests, contract drift, migration validation, secret scanning,
  or build failure.
- Long-lived branches are `master` (production, always releasable) and `master-dev`
  (test-environment deployment line). Feature work merges into `master-dev` first; production
  promotion is a reviewed merge into `master`. Changes MUST be delivered through a focused
  branch and review, use Conventional Commits, and link specification requirements to
  implementation and test evidence. Generated artifacts, unrelated refactors, and dependency
  upgrades MUST NOT be mixed into a feature change without explicit justification. Make
  environment selection remains explicit `mode=local|test|prod` and MUST NOT be inferred from
  the Git branch name.
- Releases MUST have an immutable artifact, migration order, configuration diff, rollout and
  rollback plan, observability checks, and accountable approval. Breaking API/event changes
  MUST use a new version and a documented deprecation window; destructive data changes MUST
  not precede removal of all old readers/writers.
- Emergency changes may shorten review but MUST preserve automated safety checks and MUST add
  a retrospective, missing tests, and durable remediation immediately after stabilization.

Rationale: reproducibility and controlled rollout make a change auditable and reversible
across independently deployable components.

### VIII. Chinese-First Engineering Documentation

- Project-authored Markdown documents MUST default to Simplified Chinese. This includes
  feature Spec, Plan, Tasks, Checklist, ADR, runbook, project handoff report, and
  development guidance documents under active authorship.
- Hand-written explanatory code comments MUST default to Simplified Chinese. Comments MUST
  explain design intent, constraints, invariants, failure behavior, and non-obvious reasons;
  they MUST NOT restate code syntax. Principle IV continues to govern comment substance;
  this principle governs the default language of those comments.
- Code identifiers, API field names, CLI commands, paths, environment variables, protocols,
  standards, library names, and proper nouns MUST remain in their original form and MUST NOT
  be translated solely for language consistency.
- Automatically generated files, third-party content, licenses, external contracts, and
  machine-consumed artifacts are not required to be translated.
- Unreviewed bulk translation of the existing repository is not required. Historical English
  documents may remain as-is until deliberately revised.
- When an existing English document is edited, newly added text and substantially revised
  passages MUST follow this principle. Unchanged historical English prose need not be
  rewritten solely for language alignment.

Rationale: a Chinese-first documentation and comment default matches the team's primary
working language while keeping executable identifiers, contracts, and external artifacts
stable and machine-readable.

## Technology and Architecture Constraints

- The approved baseline is Go 1.22 with Gin for `proxy-gateway`; Python 3.11 with FastAPI,
  Pydantic, async SQLAlchemy 2.x, and Alembic for domain services; React 18 with Vite and
  strict TypeScript for the single web frontend; PostgreSQL 15, Redis 7, Kafka-compatible
  messaging, and S3-compatible object storage; Prometheus, Grafana, Loki, and an error tracker
  for operations. A version upgrade or equivalent implementation is allowed through a tested
  dependency change; replacing a technology or its responsibility requires an ADR.
- Source layout and dependency direction MUST follow
  `项目开发/1-项目架构与目录结构.md` and the language-specific engineering documents under
  `项目开发/`. Where those documents conflict with this constitution, this constitution wins.
- External HTTP APIs MUST be versioned in the URL and described by OpenAPI. Responses and
  errors MUST preserve the repository-wide envelope and correlation ID unless compatibility
  with an upstream streaming protocol requires transparent pass-through; that exception MUST
  be captured in the contract.
- Kafka partition keys MUST preserve ordering for the owned aggregate. Producers MUST use
  durable acknowledgement for value-bearing events; consumers MUST use manual completion,
  deduplication, bounded retry, and a monitored dead-letter path.
- Frontend features MUST use generated or schema-checked API types, accessible semantic UI,
  explicit loading/empty/error/success states, route-level authorization, and responsive
  layouts. Client checks are usability controls and MUST NOT replace server authorization.
- Configuration MUST be injected by environment or a secret manager, validated at startup,
  and separated by environment. Defaults MUST be safe; production MUST fail closed when a
  required security or persistence setting is absent.

## Development Workflow and Quality Gates

1. **Specify**: A change MUST begin with independently testable acceptance scenarios plus
   measurable security, data, performance, reliability, and observability requirements when
   applicable. Unknowns with material impact MUST remain explicit rather than guessed.
2. **Plan**: The implementation plan MUST pass the Constitution Check before research and
   again after contracts/data design. It MUST name affected services, ownership boundaries,
   contracts, migration/rollback, threat cases, telemetry, test layers, and deployment order.
3. **Task**: Tasks MUST trace to requirements and include tests before implementation,
   contract generation/validation, migrations, observability, security checks, documentation,
   and rollout work. A user story is not complete while any required evidence is deferred.
4. **Implement**: Developers MUST make the smallest coherent change, preserve service
   boundaries, and keep generated and handwritten code distinct. Deviations MUST be recorded
   in the plan's Complexity Tracking table with a linked ADR and removal or review date.
5. **Verify**: Before merge, formatting, linting, type checks, unit/contract/integration tests,
   migration checks, secret/dependency scans, and builds for every affected component MUST
   pass. Performance, recovery, accessibility, or security tests MUST run when their governed
   behavior changes.
6. **Review and release**: Review MUST verify requirement-to-test traceability, data/security
   impact, backwards compatibility, telemetry, and rollback. Release evidence MUST identify
   the artifact, configuration/migrations, health signals, and rollback decision point.

## Governance

- This constitution is the highest engineering governance document for TokenMarket. Feature
  specs, prototype notes, plans, tasks, code comments, and schedules cannot waive it. A direct
  conflict MUST block implementation until the subordinate artifact is corrected or this
  constitution is formally amended.
- Amendments MUST be proposed as a reviewed change containing the rationale, affected
  principles/templates, migration impact, compatibility risk, and Sync Impact Report. Approval
  requires the repository owner or delegated technical maintainer; changes affecting security,
  financial correctness, or data governance require an explicit specialist review or recorded
  risk acceptance by the accountable owner.
- Constitution versions follow semantic versioning: MAJOR for removal or incompatible
  redefinition of a principle/governance guarantee; MINOR for a new principle/section or
  materially stronger obligations; PATCH for non-semantic clarification and corrections.
  Ratification remains the original adoption date; Last Amended changes on every approved
  amendment.
- Every feature plan MUST perform the Constitution Check twice. Every pull request MUST state
  compliance or list approved deviations. Every release MUST pass the quality gates above.
  A deviation MUST be specific, time-bounded, owned, monitored, and accompanied by a remediation
  issue; “prototype,” “MVP,” or schedule pressure alone is not sufficient justification.
- Compliance MUST be audited at least once per release and quarterly for mainline engineering
  practices. Expired deviations, unresolved critical security findings, unreconciled financial
  data, or untested destructive migrations block release.
- Runtime implementation guidance lives in `项目开发/1-项目架构与目录结构.md` through
  `项目开发/4-前端与DevOps监控规范.md`. These documents may add detail but MUST NOT weaken
  this constitution.

**Version**: 1.2.0 | **Ratified**: 2026-07-13 | **Last Amended**: 2026-07-23
