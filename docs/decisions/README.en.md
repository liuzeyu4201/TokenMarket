[中文](README.md) | **English**

# Architecture Decision Records

This directory records significant architectural decisions for the TokenMarket monorepo. Each ADR follows the template of `001-github-actions-ci-adapter.md`:

- Context and problem
- Decision owner and stakeholders
- Options considered
- Decision and consequences
- Failure modes, operational cost, and rollback
- Alternatives retained

Historical ADR bodies keep the language they were written in (mostly English, plus Chinese ADR 004). They are **not bulk-translated in this pass**.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-github-actions-ci-adapter.md) | GitHub Actions as a read-only thin adapter for `make ci` | Accepted |
| [002](002-local-compose-lifecycle.md) | Local dependency lifecycle via Docker Compose | Accepted (implementation Verified) |
| [003](003-layered-compose-deploy.md) | Layered Compose and isolated deploy entry | Accepted |
| [004](004-hosted-toolchain-execution-profiles.md) | Hosted toolchain execution profiles | Accepted |

## When to write an ADR

Create or update an ADR in the same PR that introduces:

- A new service or component
- A new storage system or persistence model
- A new protocol or external integration contract
- A new shared abstraction consumed by more than one component
- A new cross-service dependency

## Review rules

1. ADRs are reviewed with the PR that implements the decision.
2. The relevant component README and traceability checklist must link the ADR.
3. ADRs are immutable once merged; supersede with a new ADR rather than rewriting history.
