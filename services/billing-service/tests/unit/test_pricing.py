from __future__ import annotations

import threading

import pytest

from app.domain.pricing import (
    PriceLock,
    RateRow,
    RateVersion,
    Registry,
    SellerQuote,
    UsageInput,
    mul_bps,
    quote,
)
from app.domain.pricing.errors import PricingError


def _row(**kwargs: object) -> RateRow:
    base = dict(
        provider="openai",
        protocol="openai",
        model="gpt-test",
        endpoint_id="openai.post.v1.chat.completions",
        dimension="input_tokens",
        region="*",
        currency="USD",
        unit="token",
        rate_minor_units=2,
        valid_from=None,
        valid_to=None,
    )
    base.update(kwargs)
    return RateRow(**base)  # type: ignore[arg-type]


def _version(rows: list[RateRow] | None = None, **kwargs: object) -> RateVersion:
    data = dict(
        version_id="rv-1",
        status="draft",
        scale=6,
        currency="USD",
        buyer_multiplier_bps=12000,
        seller_quote_min_bps=8000,
        seller_quote_max_bps=11000,
        rows=rows
        or [
            _row(dimension="input_tokens", rate_minor_units=2),
            _row(dimension="output_tokens", rate_minor_units=4),
        ],
    )
    data.update(kwargs)
    return RateVersion(**data)  # type: ignore[arg-type]


def test_mul_bps_half_up() -> None:
    assert mul_bps(1, 10000) == 1
    assert mul_bps(1, 15000) == 2
    assert mul_bps(3, 10000) == 3
    assert mul_bps(9999, 10001) == 10000  # 9999 * 1.0001 = 9999.9999 → 10000


def test_quote_usage_golden() -> None:
    v = _version()
    usage = UsageInput(input_tokens=10, output_tokens=5)
    lock = PriceLock(
        request_id="r1",
        rate_version="rv-1",
        buyer_bps=12000,
        seller_bps=10000,
    )
    result = quote(usage=usage, version=v, lock=lock, reported_minor=None)
    assert result.status == "rated"
    assert result.base_minor == 10 * 2 + 5 * 4  # 40
    assert result.buyer_debit == mul_bps(40, 12000)
    assert result.seller_earning == mul_bps(40, 10000)
    assert result.spread == result.buyer_debit - result.seller_earning
    assert result.spread >= 0


def test_quote_reported_not_overwritten_by_usage() -> None:
    v = _version()
    usage = UsageInput(input_tokens=10, output_tokens=5)
    lock = PriceLock("r1", "rv-1", 12000, 10000)
    result = quote(usage=usage, version=v, lock=lock, reported_minor=7)
    assert result.status == "reported"
    assert result.base_minor == 7
    assert result.usage_base_minor == 40
    assert result.variance_minor == 40 - 7


def test_quote_missing_rate_unresolved() -> None:
    v = _version(rows=[_row(dimension="audio_ms", rate_minor_units=1)])
    usage = UsageInput(input_tokens=3)
    lock = PriceLock("r1", "rv-1", 12000, 10000)
    result = quote(usage=usage, version=v, lock=lock, reported_minor=None)
    assert result.status == "unresolved"
    assert result.unresolved_reason == "missing_rate"


def test_quote_replay_identical() -> None:
    v = _version()
    usage = UsageInput(input_tokens=8, output_tokens=1)
    lock = PriceLock("r1", "rv-1", 12000, 9000)
    a = quote(usage, v, lock, None)
    b = quote(usage, v, lock, None)
    assert a == b


def test_publish_rejects_overlap() -> None:
    reg = Registry()
    v = _version(
        rows=[
            _row(dimension="input_tokens"),
            _row(dimension="input_tokens", model="gpt-test"),
        ]
    )
    # same key twice with unbounded windows
    v.rows[1] = _row(dimension="input_tokens")
    with pytest.raises(PricingError) as exc:
        reg.create(v)
        reg.publish(v.version_id)
    assert exc.value.code == "overlap"


def test_publish_rejects_negative_spread_config() -> None:
    reg = Registry()
    v = _version(buyer_multiplier_bps=10000, seller_quote_max_bps=12000)
    with pytest.raises(PricingError) as exc:
        reg.create(v)
        reg.publish("rv-1")
    assert exc.value.code == "negative_spread"


def test_seller_quote_bounds() -> None:
    reg = Registry()
    v = _version()
    v.rows = [
        _row(dimension="input_tokens"),
        _row(dimension="output_tokens", rate_minor_units=4),
    ]
    reg.create(v)
    with pytest.raises(PricingError) as exc:
        reg.set_quote(
            SellerQuote(seller_id="s1", rate_version="rv-1", multiplier_bps=7000)
        )
    assert exc.value.code == "quote_out_of_bounds"
    reg.set_quote(
        SellerQuote(seller_id="s1", rate_version="rv-1", multiplier_bps=10000)
    )
    reg.preview("rv-1")
    reg.approve("rv-1")
    reg.publish("rv-1")


def test_published_immutable() -> None:
    reg = Registry()
    v = _version()
    v.rows = [
        _row(dimension="input_tokens"),
        _row(dimension="output_tokens", rate_minor_units=4),
    ]
    reg.create(v)
    reg.set_quote(SellerQuote("s1", "rv-1", 10000))
    reg.preview("rv-1")
    reg.approve("rv-1")
    reg.publish("rv-1")
    with pytest.raises(PricingError) as exc:
        reg.add_row("rv-1", _row(dimension="cache_read_tokens"))
    assert exc.value.code == "immutable"
    with pytest.raises(PricingError) as exc2:
        reg.delete_version("rv-1")
    assert exc2.value.code == "immutable"


def test_supersede_keeps_old_for_replay() -> None:
    reg = Registry()
    v1 = _version()
    v1.rows = [
        _row(dimension="input_tokens"),
        _row(dimension="output_tokens", rate_minor_units=4),
    ]
    reg.create(v1)
    reg.set_quote(SellerQuote("s1", "rv-1", 10000))
    reg.preview("rv-1")
    reg.approve("rv-1")
    reg.publish("rv-1")
    lock = reg.lock("req-old", "s1")
    v2 = _version(version_id="rv-2", buyer_multiplier_bps=13000)
    v2.rows = list(v1.rows)
    reg.create(v2)
    reg.set_quote(SellerQuote("s1", "rv-2", 10000))
    reg.preview("rv-2")
    reg.approve("rv-2")
    reg.publish("rv-2")
    assert reg.get("rv-1").status == "superseded"
    assert lock.rate_version == "rv-1"
    usage = UsageInput(input_tokens=2, output_tokens=2)
    old = quote(usage, reg.get("rv-1"), lock, None)
    new_lock = reg.lock("req-new", "s1")
    assert new_lock.rate_version == "rv-2"
    new = quote(usage, reg.get("rv-2"), new_lock, None)
    assert old.buyer_debit != new.buyer_debit


def test_seller_view_hides_buyer_multiplier() -> None:
    v = _version()
    view = v.seller_view(seller_bps=10000)
    assert "buyer_multiplier_bps" not in view
    assert view["seller_quote_min_bps"] == 8000
    assert view["own_multiplier_bps"] == 10000


def test_buyer_view_hides_other_quotes() -> None:
    v = _version()
    view = v.buyer_view()
    assert "seller_quotes" not in view
    assert view["buyer_multiplier_bps"] == 12000


def test_lock_without_published_fail_closed() -> None:
    reg = Registry()
    with pytest.raises(PricingError) as exc:
        reg.lock("r1", "s1")
    assert exc.value.code == "no_published"


def test_concurrent_lock_keeps_snapshot() -> None:
    reg = Registry()
    v1 = _version()
    v1.rows = [
        _row(dimension="input_tokens"),
        _row(dimension="output_tokens", rate_minor_units=4),
    ]
    reg.create(v1)
    reg.set_quote(SellerQuote("s1", "rv-1", 10000))
    reg.preview("rv-1")
    reg.approve("rv-1")
    reg.publish("rv-1")
    barrier = threading.Barrier(2)
    held: list[PriceLock] = []

    def _lock() -> None:
        barrier.wait()
        held.append(reg.lock("req-a", "s1"))

    t = threading.Thread(target=_lock)
    t.start()
    barrier.wait()
    v2 = _version(version_id="rv-2", buyer_multiplier_bps=15000)
    v2.rows = list(v1.rows)
    reg.create(v2)
    reg.set_quote(SellerQuote("s1", "rv-2", 10000))
    reg.preview("rv-2")
    reg.approve("rv-2")
    reg.publish("rv-2")
    t.join()
    assert held[0].rate_version in {"rv-1", "rv-2"}
    assert held[0].buyer_bps in {12000, 15000}
    if held[0].rate_version == "rv-1":
        assert held[0].buyer_bps == 12000
    else:
        assert held[0].buyer_bps == 15000
