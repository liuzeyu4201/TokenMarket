from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.ledger import LedgerError, LedgerService, account_id_for
from app.domain.recon import EvidenceEvent, ReconService


def _ready() -> tuple[LedgerService, ReconService]:
    led = LedgerService()
    led.seed_quota(
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        account_grant=10000,
        project_grant=10000,
        key_grant=10000,
    )
    recon = ReconService(led, variance_threshold=5, sla=timedelta(hours=1))
    return led, recon


def _reserve(led: LedgerService, rid: str, amount: int = 100) -> None:
    led.reserve(
        request_id=rid,
        idempotency_key=rid,
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        amount_minor=amount,
        rate_version="lock-v1",
    )


def _money(kind: str, rid: str, buyer: int, seller: int, spread: int) -> EvidenceEvent:
    return EvidenceEvent(
        event_id=f"{kind}-{rid}",
        request_id=rid,
        kind=kind,  # type: ignore[arg-type]
        buyer_debit=buyer,
        seller_earning=seller,
        spread=spread,
        seller_id="seller-1",
        rate_version="ignored-new",
        evidence_digest="ev",
        connection_id="conn-old",
        computed_buyer=buyer if kind == "reported_cost" else None,
    )


def test_duplicate_and_out_of_order_do_not_double_settle() -> None:
    led, recon = _ready()
    _reserve(led, "r1", 200)
    recon.ingest(_money("usage_rated", "r1", 80, 64, 16))
    recon.ingest(_money("usage_rated", "r1", 80, 64, 16))  # same event_id
    late = EvidenceEvent(
        event_id="reported-r1",
        request_id="r1",
        kind="reported_cost",
        buyer_debit=100,
        seller_earning=80,
        spread=20,
        seller_id="seller-1",
        computed_buyer=80,
        connection_id="conn-old",
    )
    recon.ingest(late)
    recon.ingest(late)
    buyer_debits = [
        e
        for e in led.entries()
        if e.request_id == "r1"
        and e.status == "settled"
        and e.direction == "debit"
        and e.account_kind == "buyer_quota"
    ]
    # original 80 plus delta 20; originals remain
    assert any(e.amount_minor_units == 80 for e in buyer_debits)
    assert led.net_settled("r1", "buyer_quota")[0] == 100
    assert led.net_settled("r1", "seller_earning")[1] == 80
    tickets = [t for t in recon.tickets() if t.kind == "VARIANCE"]
    assert tickets
    assert tickets[0].reported_minor == 100
    assert tickets[0].computed_minor == 80


def test_reported_first_usage_later_does_not_resettle() -> None:
    led, recon = _ready()
    _reserve(led, "r2")
    recon.ingest(_money("reported_cost", "r2", 50, 40, 10))
    recon.ingest(
        EvidenceEvent(
            event_id="usage-r2",
            request_id="r2",
            kind="usage_rated",
            buyer_debit=50,
            seller_earning=40,
            spread=10,
            seller_id="seller-1",
        )
    )
    settled = [
        e
        for e in led.entries()
        if e.request_id == "r2"
        and e.status == "settled"
        and e.account_kind == "buyer_quota"
        and e.direction == "debit"
    ]
    assert len(settled) == 1
    assert settled[0].rate_version == "lock-v1"


def test_four_unresolved_reasons_do_not_zero() -> None:
    led, recon = _ready()
    kinds = {
        "missing_amount": "MISSING_AMOUNT",
        "missing_usage": "MISSING_USAGE",
        "parse_failed": "PARSE_FAILED",
        "async_pending": "ASYNC_INCOMPLETE",
    }
    for i, (kind, code) in enumerate(kinds.items()):
        rid = f"u{i}"
        _reserve(led, rid, 30)
        case = recon.ingest(
            EvidenceEvent(
                event_id=f"e-{rid}",
                request_id=rid,
                kind=kind,  # type: ignore[arg-type]
                connection_id="conn-old",
            )
        )
        assert case is not None
        assert case.reason_code == code  # type: ignore[union-attr]
        assert case.amount_exposure_minor == 30  # type: ignore[union-attr]
        assert led.rebuild(account_id_for("key_quota", "key-1")).reserved >= 30


def test_tick_recovers_with_original_rate_version() -> None:
    clock = {"t": datetime(2026, 8, 31, tzinfo=timezone.utc)}

    def now() -> datetime:
        return clock["t"]

    led = LedgerService()
    led.seed_quota(
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        account_grant=1000,
        project_grant=1000,
        key_grant=1000,
    )
    recon = ReconService(led, sla=timedelta(hours=1), now=now)
    _reserve(led, "late", 80)
    recon.ingest(
        EvidenceEvent(
            event_id="p1",
            request_id="late",
            kind="async_pending",
            connection_id="conn-old",
        )
    )
    recon.ingest(
        EvidenceEvent(
            event_id="cost-late",
            request_id="late",
            kind="reported_cost",
            buyer_debit=40,
            seller_earning=32,
            spread=8,
            seller_id="seller-1",
            rate_version="should-ignore",
        )
    )
    rec = led._require_res("late")
    assert rec.status == "consumed"
    settled = [
        e
        for e in led.entries()
        if e.request_id == "late" and e.status == "settled" and e.direction == "debit"
    ]
    assert all(e.rate_version == "lock-v1" for e in settled)
    assert recon.cases()[0].status == "recovered"
    assert recon.cases()[0].connection_id == "conn-old"


def test_sla_expiry_stays_unresolved_not_zero() -> None:
    clock = {"t": datetime(2026, 8, 31, tzinfo=timezone.utc)}

    def now() -> datetime:
        return clock["t"]

    led = LedgerService()
    led.seed_quota(
        account_id="acct-1",
        project_id="proj-1",
        key_id="key-1",
        account_grant=500,
        project_grant=500,
        key_grant=500,
    )
    recon = ReconService(led, sla=timedelta(minutes=10), now=now)
    _reserve(led, "stuck", 40)
    recon.ingest(EvidenceEvent(event_id="pf", request_id="stuck", kind="parse_failed"))
    clock["t"] = clock["t"] + timedelta(minutes=11)
    recon.tick()
    rec = led._require_res("stuck")
    assert rec.status == "unresolved"
    case = recon.cases()[0]
    assert case.status == "manual"
    assert case.owner == "billing-oncall"
    assert led.rebuild(account_id_for("key_quota", "key-1")).available == 460


def test_manual_reverse_requires_step_up_and_keeps_originals() -> None:
    led, recon = _ready()
    _reserve(led, "rev", 60)
    recon.ingest(_money("reported_cost", "rev", 60, 48, 12))
    originals = {e.entry_id for e in led.entries() if e.request_id == "rev"}
    preview = recon.preview_reverse("rev")
    with pytest.raises(LedgerError) as denied:
        recon.apply_reverse(
            request_id="rev",
            actor="admin-1",
            role="admin",
            step_up=False,
            reason="fix",
            preview_id=preview.preview_id,
        )
    assert denied.value.code == "STEP_UP_REQUIRED"
    with pytest.raises(LedgerError) as role:
        recon.apply_reverse(
            request_id="rev",
            actor="buyer-1",
            role="buyer",
            step_up=True,
            reason="fix",
            preview_id=preview.preview_id,
        )
    assert role.value.code == "FORBIDDEN_ROLE"
    journal = recon.apply_reverse(
        request_id="rev",
        actor="admin-1",
        role="admin",
        step_up=True,
        reason="vendor mismatch",
        preview_id=preview.preview_id,
    )
    still = {e.entry_id for e in led.entries()}
    assert originals.issubset(still)
    assert any(e.status == "reversed" for e in led.entries())
    assert led.net_settled("rev", "buyer_quota")[0] == 0
    assert recon.audits()[0]["reason"] == "vendor mismatch"
    assert journal.journal_id


def test_daily_recon_balanced_and_orphan() -> None:
    led, recon = _ready()
    _reserve(led, "ok", 20)
    recon.ingest(_money("reported_cost", "ok", 20, 16, 4))
    _reserve(led, "orphan", 10)
    report = recon.daily_report()
    assert report.balanced is True
    assert "orphan" in report.orphan_request_ids
    assert "ok" not in report.orphan_request_ids
    assert any(t.kind == "ORPHAN" for t in recon.tickets())
