from __future__ import annotations

from app.domain.ledger import LedgerService


def test_project_overview_matches_ledger_and_keeps_unresolved() -> None:
    led = LedgerService()
    led.seed_quota(
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        account_grant=1000,
        project_grant=1000,
        key_grant=1000,
    )
    led.reserve(
        request_id="ok",
        idempotency_key="ok",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=100,
        rate_version="rv-1",
    )
    led.settle(
        request_id="ok",
        buyer_debit=80,
        seller_earning=64,
        spread=16,
        seller_id="s1",
        rate_version="rv-1",
    )
    led.reserve(
        request_id="un",
        idempotency_key="un",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=30,
        rate_version="rv-1",
    )
    led.mark_unresolved(request_id="un", reason="PARSE_FAILED")
    view = led.project_overview("proj-1")
    assert view["settled"] == 80
    assert view["unresolved"] == 30
    assert view["unresolved"] != 0
    assert view["available"] == 1000 - 80 - 30
    ids = {row["request_id"] for row in view["requests"]}  # type: ignore[union-attr]
    assert ids == {"ok", "un"}
    rows = view["requests"]
    un = next(r for r in rows if r["request_id"] == "un")  # type: ignore[index]
    assert un["reason"] == "PARSE_FAILED"
    assert un["amount_minor"] == 30
