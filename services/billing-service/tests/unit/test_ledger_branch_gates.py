"""Branch coverage for ledger reserve/settle/delta/overview fail-closed paths."""

from __future__ import annotations

import pytest

from app.domain.ledger import LedgerError, LedgerService, account_id_for
from app.domain.ledger.store import MemoryLedgerStore


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


def test_seed_quota_rejects_negative_grants() -> None:
    led = LedgerService()
    with pytest.raises(LedgerError) as exc:
        led.seed_quota(
            account_id="a",
            project_id="p",
            key_id="k",
            account_grant=10,
            project_grant=-1,
            key_grant=10,
        )
    assert exc.value.code == "VALIDATION"


def test_reserve_validates_amount_and_ids() -> None:
    led = _ledger()
    with pytest.raises(LedgerError) as exc:
        led.reserve(
            request_id="",
            idempotency_key="k",
            account_id="acct-1",
            project_id="proj-1",
            key_id="key-1",
            amount_minor=0,
            rate_version="rv-1",
        )
    assert exc.value.code == "VALIDATION"


def test_reserve_idempotency_conflicts() -> None:
    led = _ledger()
    led.reserve(
        request_id="r1",
        idempotency_key="idem-a",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=10,
        rate_version="rv-1",
    )
    with pytest.raises(LedgerError) as key_mismatch:
        led.reserve(
            request_id="r1",
            idempotency_key="idem-other",
            account_id="acct-1",
            project_id="proj-1",
            key_id="key-1",
            amount_minor=10,
            rate_version="rv-1",
        )
    assert key_mismatch.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(LedgerError) as amount_mismatch:
        led.reserve(
            request_id="r1",
            idempotency_key="idem-a",
            account_id="acct-1",
            project_id="proj-1",
            key_id="key-1",
            amount_minor=11,
            rate_version="rv-1",
        )
    assert amount_mismatch.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(LedgerError) as request_mismatch:
        led.reserve(
            request_id="r2",
            idempotency_key="idem-a",
            account_id="acct-1",
            project_id="proj-1",
            key_id="key-1",
            amount_minor=10,
            rate_version="rv-1",
        )
    assert request_mismatch.value.code == "IDEMPOTENCY_CONFLICT"


def test_settle_negative_and_released_terminal() -> None:
    led = _ledger()
    led.reserve(
        request_id="neg",
        idempotency_key="neg",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=10,
        rate_version="rv-1",
    )
    with pytest.raises(LedgerError) as unbalanced:
        led.settle(
            request_id="neg",
            buyer_debit=10,
            seller_earning=20,
            spread=-10,
            seller_id="s",
            rate_version="rv-1",
        )
    assert unbalanced.value.code == "VALIDATION"
    led.release(request_id="neg")
    with pytest.raises(LedgerError) as terminal:
        led.settle(
            request_id="neg",
            buyer_debit=10,
            seller_earning=8,
            spread=2,
            seller_id="s",
            rate_version="rv-1",
        )
    assert terminal.value.code == "ALREADY_TERMINAL"


def test_unresolved_idempotent_and_blocks_after_settle() -> None:
    led = _ledger()
    led.reserve(
        request_id="u1",
        idempotency_key="u1",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=15,
        rate_version="rv-1",
    )
    first = led.mark_unresolved(request_id="u1", reason="")
    again = led.mark_unresolved(request_id="u1", reason="again")
    assert first.status == again.status == "unresolved"
    assert first.unresolved_reason == "unknown_cost"
    led.reserve(
        request_id="u2",
        idempotency_key="u2",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=15,
        rate_version="rv-1",
    )
    led.settle(
        request_id="u2",
        buyer_debit=15,
        seller_earning=12,
        spread=3,
        seller_id="s",
        rate_version="rv-1",
    )
    with pytest.raises(LedgerError) as terminal:
        led.mark_unresolved(request_id="u2", reason="late")
    assert terminal.value.code == "ALREADY_TERMINAL"


def test_apply_delta_increase_decrease_and_noop() -> None:
    led = _ledger()
    led.reserve(
        request_id="d1",
        idempotency_key="d1",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=100,
        rate_version="rv-1",
    )
    held = led.apply_delta(
        request_id="d1",
        buyer_debit=40,
        seller_earning=30,
        spread=10,
        seller_id="seller-1",
        rate_version="rv-1",
        evidence_digest="e1",
    )
    assert held.entry_ids
    noop = led.apply_delta(
        request_id="d1",
        buyer_debit=40,
        seller_earning=30,
        spread=10,
        seller_id="seller-1",
        rate_version="rv-1",
    )
    assert noop.journal_id == held.journal_id
    up = led.apply_delta(
        request_id="d1",
        buyer_debit=70,
        seller_earning=50,
        spread=20,
        seller_id="seller-1",
        rate_version="rv-1",
    )
    assert up.entry_ids
    buyer = led.rebuild(account_id_for("buyer_quota", "acct-1"))
    assert buyer.settled_debit == 70
    down = led.apply_delta(
        request_id="d1",
        buyer_debit=50,
        seller_earning=40,
        spread=10,
        seller_id="seller-1",
        rate_version="rv-1",
    )
    assert down.entry_ids
    reversed_credits = [
        e
        for e in led.entries()
        if e.status == "reversed" and e.direction == "credit" and e.request_id == "d1"
    ]
    assert reversed_credits
    net_debit, _ = led.net_settled("d1", "buyer_quota")
    assert net_debit == 50
    with pytest.raises(LedgerError) as unbalanced:
        led.apply_delta(
            request_id="d1",
            buyer_debit=10,
            seller_earning=1,
            spread=1,
            seller_id="seller-1",
            rate_version="rv-1",
        )
    assert unbalanced.value.code == "UNBALANCED"


def test_reverse_requires_consumed_settled_legs() -> None:
    led = _ledger()
    led.reserve(
        request_id="rev-hold",
        idempotency_key="rev-hold",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=12,
        rate_version="rv-1",
    )
    with pytest.raises(LedgerError) as held:
        led.reverse(request_id="rev-hold")
    assert held.value.code == "ALREADY_TERMINAL"
    with pytest.raises(LedgerError) as missing:
        led.reverse(request_id="no-such")
    assert missing.value.code == "NOT_FOUND"


def test_project_overview_splits_held_unresolved_and_other_projects() -> None:
    led = _ledger()
    led.seed_quota(
        account_id="acct-1",
        project_id="proj-2",
        key_id="key-2",
        account_grant=0,
        project_grant=200,
        key_grant=200,
    )
    led.reserve(
        request_id="hold",
        idempotency_key="hold",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=20,
        rate_version="rv-1",
    )
    led.reserve(
        request_id="open",
        idempotency_key="open",
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=10,
        rate_version="rv-1",
    )
    led.mark_unresolved(request_id="open", reason="missing_cost")
    led.reserve(
        request_id="other",
        idempotency_key="other",
        account_id="acct-1",
        project_id="proj-2",
        key_id="key-2",
        amount_minor=5,
        rate_version="rv-1",
    )
    overview = led.project_overview("proj-1")
    assert overview["reserved"] == 20
    assert overview["unresolved"] == 10
    requests = overview["requests"]
    ids = {row["request_id"] for row in requests}  # type: ignore[union-attr]
    assert ids == {"hold", "open"}
    assert "other" not in ids


def test_post_rejects_negative_amount() -> None:
    led = _ledger()
    with pytest.raises(LedgerError) as exc:
        led._post(
            journal_id="j",
            request_id="r",
            account_id="acct",
            kind="buyer_quota",
            amount=-1,
            direction="debit",
            status="settled",
            rate_version="rv-1",
        )
    assert exc.value.code == "VALIDATION"


def test_store_idempotency_miss_and_save_unknown() -> None:
    store = MemoryLedgerStore()
    assert store.get_by_idempotency("missing") is None
    led = LedgerService(store)
    led.seed_quota(
        account_id="a",
        project_id="p",
        key_id="k",
        account_grant=10,
        project_grant=10,
        key_grant=10,
    )
    reserved = led.reserve(
        request_id="s1",
        idempotency_key="s1",
        account_id="a",
        project_id="p",
        key_id="k",
        amount_minor=1,
        rate_version="rv-1",
    )
    assert store.get_by_idempotency("s1") is not None
    reserved.request_id = "ghost"
    with pytest.raises(KeyError):
        store.save_reservation(reserved)
