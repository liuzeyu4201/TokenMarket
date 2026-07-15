# API and Event Contracts

This directory holds public API, event, and schema contracts for the TokenMarket
platform.

## Contract-first rule

Any OpenAPI specification, event schema, or typed message contract must be
reviewed and versioned here before a consumer or producer is implemented.

## Version compatibility

- Contracts follow semantic versioning.
- A minor version bump may only add optional fields.
- A major version bump is required for breaking field, type, or behavior changes.
- Deprecated fields must be retained for at least one major version and marked
  with a `deprecated` annotation.

## Generated types

- Consumer-side generated types must be produced from the canonical contract in
  this directory, never hand-written to match a running service.
- Generated artifacts are checked in under `shared/contracts/` with a source
  mapping back to the canonical contract file.
- Drift between a generated artifact and its source contract blocks the build.

## Ownership

- API and event contracts are owned by the feature team that introduces them.
- Cross-service contracts require review from both producing and consuming team
  owners.
