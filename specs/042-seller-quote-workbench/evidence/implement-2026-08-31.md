# Implementation evidence: 042-seller-quote-workbench

**Date**: 2026-08-31

## Tests

- API `test_workbench.py` + `test_workbench_http.py`: 8 passed; workbench domain+HTTP **92%**.
- Frontend `Supply.test.tsx` + AppShell/App: 16 passed in those files.

## Behaviors

- In-bounds quote appends seq; 7000/13000 rejected; 10500 with buyer=10000 is NEGATIVE_SPREAD.
- Capacity 0 and paused lifecycle set admits_new false.
- Public card has no buyer_multiplier / buyer_id / raw_body.
- Unresolved count isolated from settled_minor.
- Quote rate limit 2/window; audit records before/after.
- Buyer workspace GET 403.

UI verified with vitest (no interactive browser in this environment).
