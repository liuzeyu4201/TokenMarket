"""Local/test synthetic SMS adapter — never used in production readiness."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.observability import redact_message
from app.sms.port import SmsDeliveryRequest, SmsDeliveryResult

if TYPE_CHECKING:
    from app.config import AuthSettings, ModeName

logger = logging.getLogger("api-service")


class SyntheticSmsAdapter:
    """Accepts delivery without contacting a real provider.

    Logs only non-sensitive correlation fields. Destination and OTP never appear
    in log records.
    """

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.calls: list[uuid.UUID] = []

    async def send(self, request: SmsDeliveryRequest) -> SmsDeliveryResult:
        # Intentionally ignore destination/code; only record opaque ref.
        self.calls.append(request.provider_request_ref)
        logger.info(
            redact_message(
                "synthetic sms accepted "
                f"provider_request_ref={request.provider_request_ref} "
                f"request_id={request.request_id}"
            )
        )
        return SmsDeliveryResult.accepted(
            safe_provider_ref=f"synthetic:{request.provider_request_ref}"
        )

    async def query_status(
        self, provider_request_ref: uuid.UUID
    ) -> SmsDeliveryResult | None:
        if provider_request_ref in self.calls:
            return SmsDeliveryResult.accepted(
                safe_provider_ref=f"synthetic:{provider_request_ref}"
            )
        return None

    def provider_health_ok(self) -> bool:
        return True


class ProductionBlockedSmsAdapter:
    """Fail-closed adapter when production has no approved real provider."""

    async def send(self, request: SmsDeliveryRequest) -> SmsDeliveryResult:
        del request  # unused; never deliver
        return SmsDeliveryResult.unavailable()

    async def query_status(
        self, provider_request_ref: uuid.UUID
    ) -> SmsDeliveryResult | None:
        del provider_request_ref
        return None

    def provider_health_ok(self) -> bool:
        return False


def build_sms_adapter(
    settings: AuthSettings,
    *,
    mode: ModeName | None = None,
    override: object | None = None,
) -> object:
    """Construct the SMS adapter for the process environment.

    Production with synthetic/fake fails closed (health false / blocked adapter).
    Local/test may use synthetic. Tests inject *override* (e.g. BlockingSmsFake).
    """
    if override is not None:
        return override

    from app.config import resolve_app_mode

    effective = mode if mode is not None else resolve_app_mode()
    adapter_name = (settings.sms_adapter or "").strip().lower()
    timeout = float(settings.sms_provider_timeout_seconds)

    if effective in ("test", "prod"):
        if adapter_name in {"synthetic", "fake", "test"}:
            return ProductionBlockedSmsAdapter()
        # Approved real adapters are not implemented in this feature slice.
        return ProductionBlockedSmsAdapter()

    if adapter_name in {"synthetic", "fake", "test", ""}:
        return SyntheticSmsAdapter(timeout_seconds=timeout)

    return ProductionBlockedSmsAdapter()
