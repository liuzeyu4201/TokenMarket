# Data Model

## UnresolvedCase

request_id, reason_code, missing_evidence, amount_exposure_minor, next_action, retry_at, owner, sla_until, connection_id, rate_version, status open|recovered|manual

## EvidenceEvent

event_id, request_id, kind (reported_cost|usage_rated|parse_failed|async_pending|missing_amount|missing_usage)

## ReconTicket

ticket_id, kind VARIANCE|ORPHAN|UNBALANCED, request_id, detail, created_at

## ReversePreview

preview_id, request_id, original_entry_ids, net_buyer_delta
