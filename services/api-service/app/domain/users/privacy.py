"""Phone masking helpers — never log or return full MSISDN."""

from __future__ import annotations


def mask_phone(phone_normalized: str) -> str:
    """Mask all but last four digits of an 11-digit CN mobile."""
    if len(phone_normalized) < 4:
        return "****"
    return "*" * (len(phone_normalized) - 4) + phone_normalized[-4:]
