from __future__ import annotations

import pytest

from app.domain.workbench.service import (
    ConnectionSnapshot,
    PlatformBounds,
    WorkbenchError,
    WorkbenchService,
)


def _svc(**kwargs: object) -> WorkbenchService:
    return WorkbenchService(PlatformBounds(), **kwargs)  # type: ignore[arg-type]


def _snap(**kwargs: object) -> ConnectionSnapshot:
    data = dict(
        connection_id="c1",
        seller_account_id="s1",
        provider="openai",
        supply_mode="shared",
        lifecycle_state="listed",
        health_state="healthy",
        health_reason=None,
    )
    data.update(kwargs)
    return ConnectionSnapshot(**data)  # type: ignore[arg-type]


def test_quote_within_bounds_appends_seq() -> None:
    wb = _svc()
    a = wb.submit_quote(
        seller_id="s1",
        connection_id="c1",
        multiplier_bps=10000,
        actor_id="s1",
        owner_id="s1",
    )
    b = wb.submit_quote(
        seller_id="s1",
        connection_id="c1",
        multiplier_bps=10500,
        actor_id="s1",
        owner_id="s1",
    )
    assert a.seq == 1 and b.seq == 2
    hist = wb.history("c1", "s1", "s1")
    assert [h["seq"] for h in hist] == [1, 2]
    assert hist[0]["multiplier_bps"] == 10000


def test_quote_out_of_bounds_and_negative_spread() -> None:
    wb = _svc()
    with pytest.raises(WorkbenchError) as low:
        wb.submit_quote(
            seller_id="s1",
            connection_id="c1",
            multiplier_bps=7000,
            actor_id="s1",
            owner_id="s1",
        )
    assert low.value.code == "QUOTE_OUT_OF_BOUNDS"
    with pytest.raises(WorkbenchError) as hi:
        wb.submit_quote(
            seller_id="s1",
            connection_id="c1",
            multiplier_bps=13000,
            actor_id="s1",
            owner_id="s1",
        )
    assert hi.value.code == "QUOTE_OUT_OF_BOUNDS"
    tight = WorkbenchService(
        PlatformBounds(
            buyer_multiplier_bps=10000,
            seller_quote_min_bps=8000,
            seller_quote_max_bps=11000,
        )
    )
    with pytest.raises(WorkbenchError) as spread:
        tight.submit_quote(
            seller_id="s1",
            connection_id="c1",
            multiplier_bps=10500,
            actor_id="s1",
            owner_id="s1",
        )
    assert spread.value.code == "NEGATIVE_SPREAD"
    assert wb.history("c1", "s1", "s1") == []


def test_capacity_zero_stops_new_shared() -> None:
    wb = _svc()
    snap = _snap()
    assert wb.card(snap, "s1")["admits_new"] is True
    wb.set_capacity(
        seller_id="s1",
        connection_id="c1",
        declared_capacity=0,
        actor_id="s1",
        owner_id="s1",
    )
    assert wb.card(snap, "s1")["admits_new"] is False
    paused = _snap(lifecycle_state="paused")
    wb.set_capacity(
        seller_id="s1",
        connection_id="c1",
        declared_capacity=10,
        actor_id="s1",
        owner_id="s1",
    )
    assert wb.card(paused, "s1")["admits_new"] is False


def test_card_privacy_and_unresolved_not_settled() -> None:
    wb = _svc()
    wb.record_unresolved("c1", "parse_failed")
    wb.record_settled("c1", 50)
    public = wb.card(_snap(), "s1")
    blob = str(public).lower()
    assert "buyer_multiplier" not in blob
    assert "buyer_id" not in blob
    assert "raw_body" not in blob
    assert public["earnings"]["settled_minor"] == 50
    assert public["earnings"]["unresolved_count"] == 1
    assert "parse_failed" in public["earnings"]["unresolved_reasons"]
    assert public["earnings"]["settled_minor"] != public["earnings"]["unresolved_count"]


def test_audit_and_rate_limit() -> None:
    wb = _svc(quote_limit=2, quote_window_s=60.0)
    wb.submit_quote(
        seller_id="s1",
        connection_id="c1",
        multiplier_bps=9000,
        actor_id="act",
        owner_id="s1",
    )
    wb.submit_quote(
        seller_id="s1",
        connection_id="c1",
        multiplier_bps=9100,
        actor_id="act",
        owner_id="s1",
    )
    with pytest.raises(WorkbenchError) as exc:
        wb.submit_quote(
            seller_id="s1",
            connection_id="c1",
            multiplier_bps=9200,
            actor_id="act",
            owner_id="s1",
        )
    assert exc.value.code == "RATE_LIMITED"
    events = wb.audits("c1")
    assert len(events) == 2
    assert events[0].action == "quote"
    assert events[1].after["seq"] == 2


def test_foreign_owner_forbidden() -> None:
    wb = _svc()
    with pytest.raises(WorkbenchError) as exc:
        wb.submit_quote(
            seller_id="s1",
            connection_id="c1",
            multiplier_bps=10000,
            actor_id="s1",
            owner_id="other",
        )
    assert exc.value.code == "FORBIDDEN"
