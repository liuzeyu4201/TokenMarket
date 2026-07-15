# Shared Contracts

This directory holds versioned cross-component contracts. Contracts are the
single source of truth for HTTP APIs, events, shared schemas and developer
workflow definitions.

## Ownership and versioning

- Every contract has an owner, semantic version and compatibility statement.
- Consumers must generate types from these contracts; copied models are not
  allowed.
- Breaking changes require a new major/minor version and a documented
  deprecation window.

## Current contracts

| Path | Owner | Version | Format |
|------|-------|---------|--------|
| `repository-workflow/v1/` | Repository maintainers | 1.0.0 | JSON Schema / Markdown |
