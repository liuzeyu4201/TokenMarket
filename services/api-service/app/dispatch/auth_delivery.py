"""Bounded-batch SMS delivery dispatcher with lease and graceful stop."""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import AuthSettings
from app.domain.authentication.delivery_service import DeliveryService
from app.observability import (
    emit_auth_event,
    record_auth_dispatcher_claim,
    redact_message,
)
from app.repositories.authentication import AuthenticationRepository, utc_now
from app.security.reference import phone_ref
from app.sms.port import SmsDeliveryPort

logger = logging.getLogger("api-service")


class AuthDeliveryDispatcher:
    """Claim pending challenges, send once, finalize; stop drains started work."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: AuthSettings,
        sms: SmsDeliveryPort,
        *,
        owner: str | None = None,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._sms = sms
        self.owner = owner or f"dispatcher-{secrets.token_hex(8)}"
        self._poll_interval = poll_interval_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._in_flight = 0
        self._started_refs: set[uuid.UUID] = set()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._run_loop(), name="auth-delivery-dispatcher"
        )

    async def stop(self, *, drain_seconds: float | None = None) -> None:
        self._stop.set()
        budget = (
            float(drain_seconds)
            if drain_seconds is not None
            else float(self._settings.dispatcher_drain_seconds)
        )
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=max(budget, 0.1))
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

    async def run_once(self) -> int:
        """Claim and process one batch; returns number of items handled.

        Useful for tests that drive the dispatcher without the background loop.
        """
        if self._stop.is_set():
            return 0
        return await self._claim_and_process()

    async def recover_stale_dispatching(self) -> int:
        """Query-or-invalidate work that already has send_started_at (no resend)."""
        count = 0
        async with self._session_factory() as session:
            repo = AuthenticationRepository(session)
            cutoff = utc_now() - timedelta(
                seconds=self._settings.dispatcher_lease_seconds
            )
            stale = await repo.list_stale_dispatching(older_than=cutoff)
            await session.commit()

        for ch in stale:
            async with self._session_factory() as session:
                delivery = DeliveryService(session, self._settings, self._sms)
                await delivery.invalidate_after_send_started(
                    ch.id,
                    request_id=f"recovery-{self.owner}",
                    reason="query_or_invalidate",
                )
                count += 1
        return count

    async def _run_loop(self) -> None:
        logger.info(
            redact_message(f"auth delivery dispatcher started owner={self.owner}")
        )
        try:
            while not self._stop.is_set():
                try:
                    handled = await self._claim_and_process()
                    await self.recover_stale_dispatching()
                except Exception as exc:  # noqa: BLE001 — keep loop alive
                    logger.warning(
                        redact_message(
                            f"dispatcher loop error type={type(exc).__name__}"
                        )
                    )
                    handled = 0
                if handled == 0:
                    try:
                        await asyncio.wait_for(
                            self._stop.wait(), timeout=self._poll_interval
                        )
                    except asyncio.TimeoutError:
                        pass
        finally:
            logger.info(
                redact_message(f"auth delivery dispatcher stopped owner={self.owner}")
            )

    async def _claim_and_process(self) -> int:
        if self._stop.is_set():
            return 0

        batch_size = self._settings.dispatcher_batch_size
        lease_seconds = self._settings.dispatcher_lease_seconds

        async with self._session_factory() as session:
            repo = AuthenticationRepository(session)
            claimed = await repo.claim_pending_batch(
                owner=self.owner,
                lease_seconds=lease_seconds,
                batch_size=batch_size,
            )
            await session.commit()

        if not claimed:
            return 0

        now = utc_now()
        for ch in claimed:
            age = (now - ch.created_at).total_seconds()
            if ch.created_at.tzinfo is None:
                age = (now - ch.created_at.replace(tzinfo=now.tzinfo)).total_seconds()
            record_auth_dispatcher_claim("claimed", queue_age_seconds=age)
            emit_auth_event(
                logger,
                "auth.dispatcher.claim",
                request_id=f"dispatch-{ch.id}",
                result="claimed",
            )

        handled = 0
        for ch in claimed:
            if self._stop.is_set() and ch.send_started_at is None:
                # Graceful stop: do not start new sends for unclaimed-started work.
                # Lease will expire for reclaim by a later process.
                continue
            await self._process_one(ch)
            handled += 1
        return handled

    async def _process_one(self, ch: Any) -> None:
        self._in_flight += 1
        request_id = f"dispatch-{ch.id}"
        try:
            destination: str | None = None
            if ch.user_id is not None:
                async with self._session_factory() as session:
                    repo = AuthenticationRepository(session)
                    user = await repo.get_user_by_id(ch.user_id)
                    if user is not None:
                        destination = user.phone_normalized
                        # Ensure phone_ref still matches.
                        ref_mat = self._settings.key_material("reference")
                        expected = phone_ref(ref_mat.current, user.phone_normalized)
                        if expected != ch.phone_ref:
                            destination = None

            async with self._session_factory() as session:
                # Re-load challenge in this session
                repo = AuthenticationRepository(session)
                challenge = await repo.get_challenge(ch.id)
                if challenge is None:
                    return
                delivery = DeliveryService(session, self._settings, self._sms)
                if challenge.send_started_at is not None:
                    # Already started — never resend; query-or-invalidate only.
                    await delivery.invalidate_after_send_started(
                        challenge.id,
                        request_id=request_id,
                        reason="already_send_started",
                    )
                    return
                self._started_refs.add(challenge.provider_request_ref)
                await delivery.prepare_and_send(
                    challenge,
                    owner=self.owner,
                    request_id=request_id,
                    destination_phone=destination,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                redact_message(
                    f"dispatcher item error type={type(exc).__name__} "
                    f"request_id={request_id}"
                )
            )
            record_auth_dispatcher_claim("error")
        finally:
            self._in_flight -= 1
