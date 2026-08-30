# Implementation evidence: 037-openai-stable-dataplane

**Date**: 2026-08-31

## Coverage

```
affinity       87.0%
endpcatalog    84.6%
passthrough    89.9%
```

`TestOpenAIStableCatalogContractTable` generated from `LoadEmbedded(1)`: 105/105 openai stable records passed.

## Negatives

- All openai `control_plane` records return `CONTROL_PLANE_NOT_ALLOWED` with zero upstream hits.
- Uncataloged path → `ENDPOINT_NOT_CATALOGED`.
- Shared POST `/v1/files` → `DEDICATED_PROJECT_REQUIRED`.
- Preview without opt-in → `PREVIEW_NOT_ENABLED`.
- Catalog Match prefers literal `/v1/threads/runs` over `/v1/threads/{thread_id}`.

Live smoke remains skipped unless `TOKENMARKET_OPENAI_SMOKE=1` (paid; not authorized).
