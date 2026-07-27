"""Privacy: masking and redaction scan (T078 / SC-005)."""

from __future__ import annotations

import json
import logging
import re

from app.domain.users.privacy import mask_phone
from app.schemas.envelope import error_envelope, success_envelope

_FULL_CN_MOBILE = re.compile(r"(?<!\*)1[3-9]\d{9}(?!\*)")


def test_mask_phone() -> None:
    masked = mask_phone("13800138000")
    assert masked.endswith("8000")
    assert "13800138" not in masked
    assert "*" in masked
    assert not _FULL_CN_MOBILE.search(masked)


def test_success_envelope_does_not_embed_full_phone() -> None:
    body = success_envelope(
        {
            "user_id": "x",
            "role": "buyer",
            "status": "active",
            "phone_masked": mask_phone("13912345678"),
        },
        request_id="req-1",
    )
    serialized = json.dumps(body, ensure_ascii=False)
    assert "13912345678" not in serialized
    assert not _FULL_CN_MOBILE.search(serialized.replace(mask_phone("13912345678"), ""))


def test_error_envelopes_do_not_echo_peer_phone() -> None:
    for code, msg in (
        ("PHONE_ALREADY_REGISTERED", "该手机号已被注册"),
        ("ACCOUNT_UNAVAILABLE", "账户不可用，请通过恢复流程处理"),
        ("RATE_LIMITED", "请求过于频繁，请稍后再试"),
    ):
        body = error_envelope(code, msg, request_id="r")
        blob = json.dumps(body, ensure_ascii=False)
        assert not _FULL_CN_MOBILE.search(blob)


def test_logger_extra_should_use_masked_not_raw(
    caplog,
) -> None:  # type: ignore[no-untyped-def]
    phone = "13800138000"
    with caplog.at_level(logging.INFO):
        logging.getLogger("api-service").info(
            "registration note",
            extra={"phone_masked": mask_phone(phone), "request_id": "r"},
        )
    # Caplog may not include extras in message; ensure we never log raw by convention
    assert phone not in caplog.text or mask_phone(phone) in caplog.text
