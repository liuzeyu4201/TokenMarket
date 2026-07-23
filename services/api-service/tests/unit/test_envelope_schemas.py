"""Unified envelope shape."""

from __future__ import annotations

from app.schemas.envelope import error_envelope, success_envelope


def test_success_envelope_shape() -> None:
    body = success_envelope(
        {"user_id": "x"},
        request_id="req-1",
    )
    assert body["code"] == "0"
    assert body["message"] == "success"
    assert body["data"]["user_id"] == "x"
    assert body["request_id"] == "req-1"
    assert "timestamp" in body


def test_error_envelope_shape() -> None:
    body = error_envelope(
        "VALIDATION_ERROR",
        "bad",
        request_id="req-2",
        data={"errors": {"phone": ["x"]}},
    )
    assert body["code"] == "VALIDATION_ERROR"
    assert body["data"]["errors"]["phone"] == ["x"]
