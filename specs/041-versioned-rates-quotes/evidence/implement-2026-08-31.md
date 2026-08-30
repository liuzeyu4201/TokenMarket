# Implementation evidence: 041-versioned-rates-quotes

**Date**: 2026-08-31

## Tests

- Billing `tests/unit/test_pricing.py`: 14 passed; `app.domain.pricing` **91%** statements.
- Gateway `pricelock` **100%**; kernel `TestKernelLocksPriceOnAdmit` keeps lock after later Publish.

## Behaviors

- Integer half-up bps; reported cost not overwritten by usage-rated base.
- Missing rate → unresolved.
- Publish rejects overlap, quote_out_of_bounds, negative_spread; published immutable.
- Concurrent request lock is a single consistent snapshot.
- seller_view omits buyer_multiplier_bps.

Alembic `0002_pricing_versions` adds rate version/row/quote/lock tables.
