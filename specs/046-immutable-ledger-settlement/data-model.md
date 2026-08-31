# Data Model

## Reservation

request_id, idempotency_key, amounts, remaining, status held|consumed|released|unresolved, rate_version

## Entry（只追加）

entry_id, journal_id, account_id, account_kind (buyer_quota|project_quota|key_quota|seller_earning|platform_spread), request_id, amount_minor_units ≥0, direction debit|credit, status, rate_version, evidence_digest, reverses_entry_id, created_at

## Projection

account_id → available / reserved / settled_debit / settled_credit；rebuild() 从 entries 重算。
