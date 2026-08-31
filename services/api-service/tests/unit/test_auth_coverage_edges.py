"""Edge coverage for auth helpers counted in the 80% users/auth gate."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1.auth import _origin_rejected, _serialize_data
from app.domain.users.phone import _fullwidth_to_ascii_digits
from app.domain.users.privacy import mask_phone
from app.security.csrf import issue_csrf_token, verify_csrf_token
from app.security.origin import normalize_origin, origin_allowed


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


def test_csrf_session_id_forms_and_fail_closed() -> None:
    sid = uuid.uuid4()
    token = issue_csrf_token(b"k" * 32, 1, sid)
    assert verify_csrf_token(b"k" * 32, 1, sid.bytes, token)
    assert verify_csrf_token(b"k" * 32, 1, str(sid), token)
    ascii_form = str(sid).encode("ascii")
    assert verify_csrf_token(b"k" * 32, 1, ascii_form, token)
    with pytest.raises(ValueError):
        issue_csrf_token(b"", 1, sid)
    with pytest.raises(ValueError):
        issue_csrf_token(b"k" * 32, 0, sid)
    assert verify_csrf_token(b"k" * 32, 1, sid, "nodot") is False
    assert verify_csrf_token(b"k" * 32, 1, sid, "x.abc") is False
    assert verify_csrf_token(b"", 1, sid, "1.abc") is False


def test_origin_normalize_rejects_malformed() -> None:
    assert normalize_origin("") is None
    assert normalize_origin("null") is None
    assert normalize_origin("example.com") is None
    assert normalize_origin("ftp://example.com") is None
    assert normalize_origin("https://") is None
    assert normalize_origin("https://user:pass@example.com") is None
    assert normalize_origin("https://127.0.0.1:5173") == "https://127.0.0.1:5173"
    assert origin_allowed(None, ["https://127.0.0.1:5173"]) is False
    assert origin_allowed("https://127.0.0.1:5173", ["https://127.0.0.1:5173"]) is True
