# Architecture Decision Records

This directory records significant architectural decisions for the TokenMarket
monorepo. Each ADR follows the template established by
`001-github-actions-ci-adapter.md` and includes:

- Context and problem statement
- Decision owner and stakeholders
- Options considered
- Decision and consequences
- Failure modes, operational costs, and rollback path
- Alternatives retained for future review

## When to write an ADR

Create or update an ADR before introducing:

- A new service or component
- A new storage system or persistence model
- A new protocol or external integration contract
- A new shared abstraction consumed by more than one component
- A new cross-service dependency

## Review rules

1. ADRs are reviewed as part of the same PR that implements the decision.
2. ADRs must be linked from the relevant component README and from the
   implementation traceability checklist.
3. ADRs are immutable once merged; supersede them with a new ADR rather than
   rewriting history.
