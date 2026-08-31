from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.domain.ledger import LedgerError, LedgerService, account_id_for


def _ledger() -> LedgerService:
    led = LedgerService()
    led.seed_quota(
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        account_grant=1000,
        project_grant=800,
        key_grant=500,
    )
    return led


def test_concurrent_reserve_does_not_exceed_available() -> None:
    led = _ledger()
    # min grant is key=500
    accepted: list[int] = []

    def one(i: int) -> None:
        try:
            rec = led.reserve(
                request_id=f"r-{i}",
                idempotency_key=f"i-{i}",
                account_id="acct-1",
                project_id="proj-1",
                key_id="key-1",
                amount_minor=50,
                rate_version="rv-1",
            )
            accepted.append(rec.amount_minor)
        except LedgerError as exc:
            if exc.code != "INSUFFICIENT_QUOTA":
                raise

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(one, range(100)))
    assert sum(accepted) <= 500
    assert sum(accepted) == 500
    bal = led.rebuild(account_id_for("key_quota", "key-1"))
    assert bal.available == 0
    assert bal.reserved == 500


def test_idempotent_reserve_retries() -> None:
    led = _ledger()
    last = None
    for _ in range(10):
        last = led.reserve(
            request_id="same",
            idempotency_key="idem-1",
            account_id="acct-1",
            project_id="proj-1",
            key_id="key-1",
            amount_minor=100,
            rate_version="rv-1",
        )
    assert last is not None
    assert last.amount_minor == 100
    reserved = [
        e
        for e in led.entries()
        if e.status == "reserved" and e.account_kind == "key_quota"
    ]
    assert len(reserved) == 1
    assert led.rebuild(account_id_for("key_quota", "key-1")).available == 400


def test_settle_balanced_and_releases_remainder() -> None:
    led = _ledger()
    led.reserve(
        request_id="s1",
        idempotency_key="s1",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=100,
        rate_version="rv-1",
    )
    journal = led.settle(
        request_id="s1",
        buyer_debit=80,
        seller_earning=64,
        spread=16,
        seller_id="seller-1",
        rate_version="rv-1",
        evidence_digest="abc",
    )
    assert journal.entry_ids
    buyer = led.rebuild(account_id_for("buyer_quota", "acct-1"))
    seller = led.rebuild(account_id_for("seller_earning", "seller-1"))
    plat = led.rebuild(account_id_for("platform_spread", "platform"))
    assert buyer.settled_debit == 80
    assert seller.settled_credit == 64
    assert plat.settled_credit == 16
    assert buyer.settled_debit == seller.settled_credit + plat.settled_credit
    assert buyer.available == 1000 - 80
    # remainder 20 released (hold 100 released, debit 80)
    assert buyer.reserved == 0
    again = led.settle(
        request_id="s1",
        buyer_debit=80,
        seller_earning=64,
        spread=16,
        seller_id="seller-1",
        rate_version="rv-1",
    )
    settled_buyer = [
        e
        for e in led.entries()
        if e.status == "settled"
        and e.direction == "debit"
        and e.account_kind == "buyer_quota"
    ]
    assert again.journal_id == journal.journal_id
    assert len(settled_buyer) == 1


def test_unbalanced_settle_rejected() -> None:
    led = _ledger()
    led.reserve(
        request_id="u1",
        idempotency_key="u1",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=10,
        rate_version="rv-1",
    )
    with pytest.raises(LedgerError) as exc:
        led.settle(
            request_id="u1",
            buyer_debit=10,
            seller_earning=9,
            spread=0,
            seller_id="s",
            rate_version="rv-1",
        )
    assert exc.value.code == "UNBALANCED"


def test_release_restores_available() -> None:
    led = _ledger()
    led.reserve(
        request_id="rel",
        idempotency_key="rel",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=40,
        rate_version="rv-1",
    )
    led.release(request_id="rel")
    assert led.rebuild(account_id_for("key_quota", "key-1")).available == 500
    led.release(request_id="rel")  # idempotent


def test_unresolved_does_not_release() -> None:
    led = _ledger()
    led.reserve(
        request_id="un",
        idempotency_key="un",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=30,
        rate_version="rv-1",
    )
    rec = led.mark_unresolved(request_id="un", reason="missing_cost")
    assert rec.status == "unresolved"
    bal = led.rebuild(account_id_for("key_quota", "key-1"))
    assert bal.available == 470
    assert bal.reserved == 30
    with pytest.raises(LedgerError) as exc:
        led.release(request_id="un")
    assert exc.value.code == "ALREADY_TERMINAL"


def test_rebuild_matches_projection() -> None:
    led = _ledger()
    led.reserve(
        request_id="b1",
        idempotency_key="b1",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=50,
        rate_version="rv-1",
    )
    led.settle(
        request_id="b1",
        buyer_debit=40,
        seller_earning=32,
        spread=8,
        seller_id="seller-1",
        rate_version="rv-1",
    )
    acc = account_id_for("buyer_quota", "acct-1")
    assert led.projection(acc) == led.rebuild(acc)


def test_entries_are_immutable_and_reverse_appends() -> None:
    led = _ledger()
    led.reserve(
        request_id="rev",
        idempotency_key="rev",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=20,
        rate_version="rv-1",
    )
    led.settle(
        request_id="rev",
        buyer_debit=20,
        seller_earning=16,
        spread=4,
        seller_id="seller-1",
        rate_version="rv-1",
    )
    before = len(led.entries())
    original_ids = {e.entry_id for e in led.entries()}
    with pytest.raises(LedgerError) as mut:
        led.mutate_entry(next(iter(original_ids)))
    assert mut.value.code == "IMMUTABLE_ENTRY"
    with pytest.raises(LedgerError) as deleted:
        led.delete_entry(next(iter(original_ids)))
    assert deleted.value.code == "IMMUTABLE_ENTRY"
    led.reverse(request_id="rev", reason="test")
    after = led.entries()
    assert {e.entry_id for e in after[:before]} == original_ids
    assert any(e.status == "reversed" for e in after)
    assert led.rebuild(account_id_for("buyer_quota", "acct-1")).available == 1000
    assert led.rebuild(account_id_for("seller_earning", "seller-1")).available == 0


def test_any_bucket_insufficient_rejects_all() -> None:
    led = LedgerService()
    led.seed_quota(
        account_id="a",
        project_id="p",
        key_id="k",
        account_grant=100,
        project_grant=10,
        key_grant=100,
    )
    with pytest.raises(LedgerError) as exc:
        led.reserve(
            request_id="x",
            idempotency_key="x",
            account_id="a",
            project_id="p",
            key_id="k",
            amount_minor=50,
            rate_version="rv-1",
        )
    assert exc.value.code == "INSUFFICIENT_QUOTA"
    assert led.rebuild(account_id_for("buyer_quota", "a")).available == 100
    assert not [e for e in led.entries() if e.status == "reserved"]


def test_crash_between_reserve_and_settle_does_not_double_charge() -> None:
    store = LedgerService()._store
    led = LedgerService(store)
    led.seed_quota(
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        account_grant=200,
        project_grant=200,
        key_grant=200,
    )
    led.reserve(
        request_id="crash",
        idempotency_key="crash",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=70,
        rate_version="rv-1",
    )
    revived = LedgerService(store)
    again = revived.reserve(
        request_id="crash",
        idempotency_key="crash",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=70,
        rate_version="rv-1",
    )
    assert again.amount_minor == 70
    assert revived.rebuild(account_id_for("key_quota", "key-1")).available == 130
    reserved = [e for e in revived.entries() if e.status == "reserved"]
    assert len(reserved) == 3  # three buckets, once
