"""Deterministic blocking SMS fake for integration tests."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.sms.port import (
    DeliveryCategory,
    SmsDeliveryRequest,
    SmsDeliveryResult,
    SmsDeliveryStatus,
)


class BlockingSmsFake:
    """SMS adapter that can block mid-send via asyncio.Event.

    Supports both the ``SmsDeliveryPort.send(request)`` shape and a legacy
    keyword form used by fixture smoke tests.
    """

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.gate = asyncio.Event()
        self.gate.set()
        self.send_entered = asyncio.Event()
        self.calls: list[dict[str, Any]] = []
        self._result: SmsDeliveryStatus | str = SmsDeliveryStatus.accepted
        self._category: DeliveryCategory = DeliveryCategory.provider_rejected
        self._raise: BaseException | None = None

    def block(self) -> None:
        self.gate.clear()
        self.send_entered.clear()

    def unblock(self) -> None:
        self.gate.set()

    def set_result(
        self,
        result: SmsDeliveryStatus | str,
        *,
        category: DeliveryCategory | None = None,
    ) -> None:
        self._result = result
        if category is not None:
            self._category = category

    def set_exception(self, exc: BaseException | None) -> None:
        self._raise = exc

    async def send(
        self,
        request: SmsDeliveryRequest | None = None,
        *,
        destination_ref: bytes | None = None,
        code: str | None = None,
        provider_request_ref: uuid.UUID | None = None,
        timeout_seconds: float | None = None,
        destination: str | None = None,
    ) -> SmsDeliveryResult | str:
        """Port-style send or legacy keyword send (returns status string for smoke)."""
        legacy = request is None
        if request is not None:
            ref = request.provider_request_ref
            code_len = len(request.code)
            dest_marker: bytes | str | None = None
        else:
            if provider_request_ref is None:
                raise TypeError("provider_request_ref required in legacy mode")
            ref = provider_request_ref
            code_len = len(code or "")
            dest_marker = destination_ref if destination_ref is not None else destination

        self.calls.append(
            {
                "provider_request_ref": ref,
                "code_len": code_len,
                "destination_ref": dest_marker,
                "timeout_seconds": timeout_seconds
                if timeout_seconds is not None
                else self.timeout_seconds,
            }
        )
        self.send_entered.set()
        await self.gate.wait()

        if self._raise is not None:
            raise self._raise

        status = self._result
        if isinstance(status, str):
            # Legacy smoke path returns plain status string.
            if legacy:
                return status
            try:
                status = SmsDeliveryStatus(status)
            except ValueError:
                status = SmsDeliveryStatus.unknown

        if status is SmsDeliveryStatus.accepted:
            result = SmsDeliveryResult.accepted(safe_provider_ref=f"fake:{ref}")
        elif status is SmsDeliveryStatus.rejected:
            result = SmsDeliveryResult.rejected(self._category)
        elif status is SmsDeliveryStatus.unavailable:
            result = SmsDeliveryResult.unavailable(self._category)
        else:
            result = SmsDeliveryResult.unknown_result()

        if legacy:
            return result.status.value
        return result

    async def query_status(
        self, provider_request_ref: uuid.UUID
    ) -> SmsDeliveryResult | None:
        for call in self.calls:
            if call["provider_request_ref"] == provider_request_ref:
                if self._result in (
                    SmsDeliveryStatus.accepted,
                    "accepted",
                ):
                    return SmsDeliveryResult.accepted(
                        safe_provider_ref=f"fake:{provider_request_ref}"
                    )
                if self._result in (SmsDeliveryStatus.rejected, "rejected"):
                    return SmsDeliveryResult.rejected(self._category)
                if self._result in (
                    SmsDeliveryStatus.unavailable,
                    "unavailable",
                ):
                    return SmsDeliveryResult.unavailable(self._category)
                return SmsDeliveryResult.unknown_result()
        return None

    def provider_health_ok(self) -> bool:
        return True
