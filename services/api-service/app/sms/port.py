"""Provider-neutral SMS delivery port (phone-auth-session sms-delivery v1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class SmsDeliveryStatus(str, Enum):
    accepted = "accepted"
    rejected = "rejected"
    unavailable = "unavailable"
    unknown = "unknown"


class DeliveryCategory(str, Enum):
    provider_unavailable = "provider_unavailable"
    provider_timeout = "provider_timeout"
    provider_rejected = "provider_rejected"
    configuration_invalid = "configuration_invalid"
    unknown = "unknown"


@dataclass(frozen=True)
class SmsDeliveryRequest:
    """In-process delivery request; destination/code must never be logged."""

    provider_request_ref: uuid.UUID
    destination: str
    code: str
    expires_at: datetime
    template: str
    request_id: str


@dataclass(frozen=True)
class SmsDeliveryResult:
    status: SmsDeliveryStatus
    category: DeliveryCategory | None = None
    safe_provider_ref: str | None = None

    @classmethod
    def accepted(cls, safe_provider_ref: str | None = None) -> SmsDeliveryResult:
        return cls(
            status=SmsDeliveryStatus.accepted,
            safe_provider_ref=safe_provider_ref,
        )

    @classmethod
    def rejected(
        cls, category: DeliveryCategory = DeliveryCategory.provider_rejected
    ) -> SmsDeliveryResult:
        return cls(status=SmsDeliveryStatus.rejected, category=category)

    @classmethod
    def unavailable(
        cls, category: DeliveryCategory = DeliveryCategory.provider_unavailable
    ) -> SmsDeliveryResult:
        return cls(status=SmsDeliveryStatus.unavailable, category=category)

    @classmethod
    def unknown_result(cls) -> SmsDeliveryResult:
        return cls(
            status=SmsDeliveryStatus.unknown,
            category=DeliveryCategory.unknown,
        )


class SmsDeliveryPort(Protocol):
    """Adapter boundary for one-shot SMS send (no automatic resend)."""

    async def send(self, request: SmsDeliveryRequest) -> SmsDeliveryResult:
        """Deliver once; must respect timeout and never log destination/code."""
        ...

    async def query_status(
        self, provider_request_ref: uuid.UUID
    ) -> SmsDeliveryResult | None:
        """Optional status query after send_started; None if unsupported."""
        ...

    def provider_health_ok(self) -> bool:
        """Provider-wide health for anti-enumeration DELIVERY_UNAVAILABLE."""
        ...
