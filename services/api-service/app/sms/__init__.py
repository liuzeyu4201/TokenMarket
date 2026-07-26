"""SMS delivery adapters for phone authentication."""

from __future__ import annotations

from app.sms.port import (
    DeliveryCategory,
    SmsDeliveryPort,
    SmsDeliveryRequest,
    SmsDeliveryResult,
    SmsDeliveryStatus,
)
from app.sms.synthetic import SyntheticSmsAdapter, build_sms_adapter

__all__ = [
    "DeliveryCategory",
    "SmsDeliveryPort",
    "SmsDeliveryRequest",
    "SmsDeliveryResult",
    "SmsDeliveryStatus",
    "SyntheticSmsAdapter",
    "build_sms_adapter",
]
