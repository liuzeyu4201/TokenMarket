# Evidence 046

Billing: `pytest tests/unit/test_ledger.py tests/unit/test_ledger_http.py` 11 passed. `app.domain.ledger` 90%+; combined with HTTP 88%. 100 concurrent reserves sum to 500 (key grant). Idempotent reserve 10× one hold. Settle buyer=seller+spread. Rebuild equals projection. mutate/delete raise IMMUTABLE_ENTRY. Unresolved does not release.

Gateway: `go test -race ./internal/domain/passthrough/` ok, 89.4%. Insufficient quota returns 409 and does not call upstream.
