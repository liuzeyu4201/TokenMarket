"""Registration field validation and request hash."""

from __future__ import annotations

from app.domain.users.service import _request_hash, _validate_nickname


def test_request_hash_stable() -> None:
    a = _request_hash("13800138000", "昵称", "buyer")
    b = _request_hash("13800138000", "昵称", "buyer")
    assert a == b
    assert len(a) == 64


def test_request_hash_differs_on_role() -> None:
    assert _request_hash("13800138000", "n", "buyer") != _request_hash(
        "13800138000", "n", "seller"
    )


def test_nickname_rejects_control() -> None:
    from app.domain.users.service import FieldErrors

    result = _validate_nickname("bad\nname")
    assert isinstance(result, FieldErrors)


def test_nickname_ok() -> None:
    assert _validate_nickname("  用户甲  ") == "用户甲"
