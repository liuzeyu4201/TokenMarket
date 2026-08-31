"""Edge coverage for auth helpers counted in the 80% users/auth gate."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.v1.auth import _origin_rejected, _serialize_data
from app.domain.users.phone import _fullwidth_to_ascii_digits
from app.domain.users.privacy import mask_phone


def test_mask_phone_too_short() -> None:
    assert mask_phone("12") == "****"


def test_serialize_data_non_dict_and_datetime() -> None:
    assert _serialize_data(None) is None
    assert _serialize_data("raw") == "raw"
    stamp = datetime(2026, 8, 31, tzinfo=timezone.utc)
    out = _serialize_data({"t": stamp, "n": 1})
    assert isinstance(out, dict)
    assert str(out["t"]).startswith("2026-08-31")
    assert out["n"] == 1


def test_origin_rejected_fail_closed() -> None:
    settings = SimpleNamespace(browser_origin_list=["https://127.0.0.1:5173"])
    assert _origin_rejected("https://evil.example", settings) is True
    assert _origin_rejected("https://127.0.0.1:5173", settings) is False


def test_fullwidth_digits_normalize() -> None:
    assert _fullwidth_to_ascii_digits("１３８") == "138"
