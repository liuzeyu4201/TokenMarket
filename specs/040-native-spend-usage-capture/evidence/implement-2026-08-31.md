# Implementation evidence: 040-native-spend-usage-capture

**Date**: 2026-08-31

## Coverage

`usageparse` **89.9%** (`go test -race ./internal/domain/usageparse/`).
passthrough kernel capture tests passed.

Billing `tests/unit/test_usage_observation.py`: 5 passed.

## Parser

- OpenAI tokens + cost → `reported`, dual_present, 0.002 USD = 2000 micro-units.
- Anthropic/Vertex tokens → `rated`, reported_cost null.
- Missing usage → unresolved, tokens null (not 0).
- Negative tokens/cost → unresolved.
- Same body replay → identical evidence_digest.
- Catalog `none` → no settlement 0.
- SSE Anthropic message_start+delta merged.
- Kernel POST chat completions records Capture without raw_body/secrets.

Scratch coverprofile: `{SCRATCH}/sf26-cover.out` (session implementer dir).
