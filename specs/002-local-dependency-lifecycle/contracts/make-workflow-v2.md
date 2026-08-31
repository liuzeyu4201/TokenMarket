# Contract: Root Make Workflow v2 Migration

**Version**: 2.0.0
**Owner**: Repository maintainers
**Supersedes**: `shared/contracts/repository-workflow/v1/make-workflow.md` after the activation gate
**Breaking reason**: `dev` and `dev-down` change from fail-closed transition targets to successful, state-changing local lifecycle targets

## Stable surface

The root Makefile remains the only public entry. Existing target names, mode syntax, `0 = success`, non-zero failure, redaction, accessible text, JSONL availability, and all non-SF02 target behavior remain unchanged.

| Target | v2 purpose | Side effects | Success evidence |
|--------|------------|--------------|------------------|
| `dev` | Reconcile the SF02 local dependencies | Exact-workspace containers, network and declared storage after all preflight passes | PostgreSQL, Redis and Grafana each produce fresh authenticated readiness evidence within the shared deadline |
| `dev-down` | Stop the exact-workspace SF02 environment | Removes exact-project containers/orphans and temporary network; preserves PostgreSQL/Redis named volumes | No exact-project container/network remains; volume-only state is `already stopped` |

The complete configuration, identity, ordering, health, data, diagnostic and recovery rules are in [`local-environment-lifecycle.md`](./local-environment-lifecycle.md). JSONL follows the standard event envelope in [`workflow-event-v2.0.schema.json`](./workflow-event-v2.0.schema.json); current workflow-step fields live inside its strict payload rather than at the envelope root.

## Compatibility and migration window

This change is deliberately not published as v1-compatible:

1. **Announcement period**: land this v2 contract, the event v2 schema, migration notice and failing consumer tests while the executable still returns the v1 `SF02_NOT_READY` behavior. `make help` identifies the pending v2 activation and links recovery/data effects.
2. **Consumer migration gate**: update every repository-owned event reader, fixture, contract test, documentation reference and CI parser to accept v2. Contract checks enumerate those consumers; unknown or still-v1 consumers block activation.
3. **Activation**: only after lifecycle, isolation, persistence, redaction, failure-recovery and both-platform evidence pass may the implementation switch `dev`/`dev-down` to v2 semantics and make event v2 the default.
4. **Deprecation window**: retain the immutable v1 Make/event artifacts and migration notice through at least the next tagged repository release after activation. No new consumer may be added against v1 during this window. v1 remains historical documentation, not a selectable success mode for SF02, because it cannot express dependency states safely.

No dual execution is allowed: a single invocation cannot both fail with `SF02_NOT_READY` and mutate local resources. No dual JSONL stream is emitted because a strict v1 reader rejects dependency fields and cannot represent `WAITING`; consumers migrate before activation instead.

## Rollback

A reviewed rollback reactivates the v1 fail-closed implementation and v1 event output together. It may leave exact-project PostgreSQL/Redis volumes in place, but never deletes them. Re-enabling v2 requires the full activation gate again.
