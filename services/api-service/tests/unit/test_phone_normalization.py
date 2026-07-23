"""CN mobile normalization matrix (phone-normalization contract)."""

from __future__ import annotations

import pytest

from app.domain.users.phone import PhoneValidationError, normalize_cn_mobile


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("13800138000", "13800138000"),
        (" 138 0013 8000 ", "13800138000"),
        ("+8613800138000", "13800138000"),
        ("8613800138000", "13800138000"),
        ("１３８００１３８０００", "13800138000"),
    ],
)
def test_normalize_success(raw: str, expected: str) -> None:
    assert normalize_cn_mobile(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "12345", "+11234567890", "12800138000", None],
)
def test_normalize_errors(raw: str | None) -> None:
    result = normalize_cn_mobile(raw)  # type: ignore[arg-type]
    assert isinstance(result, PhoneValidationError)
