"""Authentication repository: challenges, idempotency, sessions, dispatch, audit.

Lock order (mandatory): user row → challenge row. Never lock challenge first
then user when both are required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.authentication.models import (
    AuthenticationSecurityEvent,
    AuthSession,
    VerificationChallenge,
    VerificationRequestIdempotencyRecord,
)
from app.domain.users.models import User, UserStatus

# Timing constants (data-model)
CHALLENGE_TTL = timedelta(minutes=5)
RESEND_COOLDOWN = timedelta(seconds=60)
IDEMPOTENCY_REPLAY = timedelta(seconds=60)
IDEMPOTENCY_DELETE_BUFFER = timedelta(hours=22)
SESSION_TTL = timedelta(minutes=60)
SESSION_RETENTION = timedelta(days=90)
AUDIT_RETENTION = timedelta(days=180)
CHALLENGE_DELETE_BUFFER = timedelta(hours=22)
MAX_ATTEMPTS = 5
CURRENT_CHALLENGE_STATES = ("pending_delivery", "delivered")
OPERATION_REQUEST_CODE = "request_verification_code"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthenticationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def lock_user_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def lock_user_by_phone(self, phone_normalized: str) -> User | None:
        result = await self._session.execute(
            select(User)
            .where(User.phone_normalized == phone_normalized)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_user_by_phone(self, phone_normalized: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.phone_normalized == phone_normalized)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    def is_auth_eligible(user: User | None) -> bool:
        if user is None:
            return False
        return user.status == UserStatus.active and user.is_deleted is False

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    async def try_begin_idempotency(
        self,
        *,
        key_digest: bytes,
        key_version: int,
        phone_ref: bytes,
        now: datetime | None = None,
    ) -> tuple[VerificationRequestIdempotencyRecord, bool]:
        """Insert processing row. Returns (record, is_winner).

        Loser loads the existing row for replay/conflict/expired handling.
        """
        ts = now or utc_now()
        rec_id = uuid.uuid4()
        stmt = (
            pg_insert(VerificationRequestIdempotencyRecord)
            .values(
                id=rec_id,
                operation=OPERATION_REQUEST_CODE,
                key_digest=key_digest,
                key_version=key_version,
                phone_ref=phone_ref,
                state="processing",
                http_status=None,
                result_code=None,
                result_payload=None,
                created_at=ts,
                completed_at=None,
                replay_until=ts + IDEMPOTENCY_REPLAY,
                delete_after=ts + IDEMPOTENCY_DELETE_BUFFER,
            )
            .on_conflict_do_nothing(
                index_elements=["operation", "key_version", "key_digest"]
            )
            .returning(VerificationRequestIdempotencyRecord.id)
        )
        result = await self._session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is not None:
            row = await self._session.get(
                VerificationRequestIdempotencyRecord, inserted_id
            )
            assert row is not None
            return row, True

        existing = await self.get_idempotency(
            key_digest=key_digest, key_version=key_version
        )
        assert existing is not None
        return existing, False

    async def get_idempotency(
        self, *, key_digest: bytes, key_version: int
    ) -> VerificationRequestIdempotencyRecord | None:
        result = await self._session.execute(
            select(VerificationRequestIdempotencyRecord).where(
                VerificationRequestIdempotencyRecord.operation
                == OPERATION_REQUEST_CODE,
                VerificationRequestIdempotencyRecord.key_version == key_version,
                VerificationRequestIdempotencyRecord.key_digest == key_digest,
            )
        )
        return result.scalar_one_or_none()

    async def complete_idempotency(
        self,
        record: VerificationRequestIdempotencyRecord,
        *,
        http_status: int,
        result_code: str,
        result_payload: dict[str, Any] | None,
        state: str = "succeeded",
        now: datetime | None = None,
    ) -> None:
        ts = now or utc_now()
        record.state = state
        record.http_status = http_status
        record.result_code = result_code
        record.result_payload = result_payload
        record.completed_at = ts
        await self._session.flush()

    # ------------------------------------------------------------------
    # Challenges
    # ------------------------------------------------------------------

    async def lock_latest_challenges_for_phone(
        self, phone_ref: bytes
    ) -> list[VerificationChallenge]:
        result = await self._session.execute(
            select(VerificationChallenge)
            .where(VerificationChallenge.phone_ref == phone_ref)
            .order_by(VerificationChallenge.created_at.desc())
            .with_for_update()
        )
        return list(result.scalars().all())

    async def lock_current_challenges_for_phone(
        self, phone_ref: bytes
    ) -> list[VerificationChallenge]:
        result = await self._session.execute(
            select(VerificationChallenge)
            .where(
                VerificationChallenge.phone_ref == phone_ref,
                VerificationChallenge.state.in_(CURRENT_CHALLENGE_STATES),
            )
            .with_for_update()
        )
        return list(result.scalars().all())

    async def supersede_challenges(
        self,
        challenges: Sequence[VerificationChallenge],
        *,
        now: datetime | None = None,
    ) -> int:
        ts = now or utc_now()
        count = 0
        for ch in challenges:
            if ch.state in (
                "pending_delivery",
                "dispatching",
                "delivered",
            ):
                ch.state = "superseded"
                ch.invalidated_at = ts
                ch.code_digest = None
                ch.code_salt = None
                ch.dispatch_lease_owner = None
                ch.dispatch_lease_until = None
                # CHECK: send_started_at only allowed for dispatching/delivered/failed.
                ch.send_started_at = None
                ch.dispatch_finished_at = None
                count += 1
        if count:
            await self._session.flush()
        return count

    async def insert_pending_challenge(
        self,
        *,
        challenge_id: uuid.UUID,
        user_id: uuid.UUID | None,
        idempotency_record_id: uuid.UUID,
        phone_ref: bytes,
        code_digest: bytes,
        code_salt: bytes,
        code_key_version: int,
        provider_request_ref: uuid.UUID,
        now: datetime | None = None,
    ) -> VerificationChallenge:
        ts = now or utc_now()
        expires = ts + CHALLENGE_TTL
        challenge = VerificationChallenge(
            id=challenge_id,
            user_id=user_id,
            idempotency_record_id=idempotency_record_id,
            phone_ref=phone_ref,
            code_digest=code_digest,
            code_salt=code_salt,
            code_key_version=code_key_version,
            provider_request_ref=provider_request_ref,
            attempt_count=0,
            state="pending_delivery",
            created_at=ts,
            expires_at=expires,
            delete_after=expires + CHALLENGE_DELETE_BUFFER,
        )
        self._session.add(challenge)
        await self._session.flush()
        return challenge

    async def get_challenge(
        self, challenge_id: uuid.UUID
    ) -> VerificationChallenge | None:
        return await self._session.get(VerificationChallenge, challenge_id)

    async def lock_challenge(
        self, challenge_id: uuid.UUID
    ) -> VerificationChallenge | None:
        # populate_existing: refresh identity-map rows after FOR UPDATE so a prior
        # unlocked peek cannot leave concurrent winners with a stale "delivered" state.
        result = await self._session.execute(
            select(VerificationChallenge)
            .where(VerificationChallenge.id == challenge_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def latest_challenge_for_phone(
        self, phone_ref: bytes
    ) -> VerificationChallenge | None:
        result = await self._session.execute(
            select(VerificationChallenge)
            .where(VerificationChallenge.phone_ref == phone_ref)
            .order_by(VerificationChallenge.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Dispatch claim / lease / send-started / finalize
    # ------------------------------------------------------------------

    async def claim_pending_batch(
        self,
        *,
        owner: str,
        lease_seconds: int,
        batch_size: int,
        now: datetime | None = None,
    ) -> list[VerificationChallenge]:
        """Claim pending work with FOR UPDATE SKIP LOCKED; set lease and commit caller."""
        ts = now or utc_now()
        lease_until = ts + timedelta(seconds=lease_seconds)
        # Reclaim expired pre-send leases as claimable.
        stmt: Select[tuple[VerificationChallenge]] = (
            select(VerificationChallenge)
            .where(
                VerificationChallenge.state == "pending_delivery",
                (
                    (VerificationChallenge.dispatch_lease_until.is_(None))
                    | (VerificationChallenge.dispatch_lease_until < ts)
                ),
                VerificationChallenge.send_started_at.is_(None),
            )
            .order_by(VerificationChallenge.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        for ch in rows:
            ch.dispatch_lease_owner = owner
            ch.dispatch_lease_until = lease_until
        if rows:
            await self._session.flush()
        return rows

    async def mark_send_started(
        self,
        challenge: VerificationChallenge,
        *,
        owner: str,
        now: datetime | None = None,
    ) -> bool:
        """Transition pending_delivery → dispatching with send_started_at.

        Returns False if lease lost or state changed.
        """
        ts = now or utc_now()
        if (
            challenge.state != "pending_delivery"
            or challenge.dispatch_lease_owner != owner
            or challenge.send_started_at is not None
        ):
            return False
        if challenge.dispatch_lease_until is not None:
            until = challenge.dispatch_lease_until
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until < ts:
                return False
        challenge.state = "dispatching"
        challenge.send_started_at = ts
        await self._session.flush()
        return True

    async def finalize_delivered(
        self,
        challenge: VerificationChallenge,
        *,
        now: datetime | None = None,
    ) -> None:
        ts = now or utc_now()
        challenge.state = "delivered"
        challenge.delivered_at = ts
        challenge.dispatch_finished_at = ts
        challenge.dispatch_lease_owner = None
        challenge.dispatch_lease_until = None
        await self._session.flush()

    async def finalize_delivery_failed(
        self,
        challenge: VerificationChallenge,
        *,
        clear_otp: bool = True,
        now: datetime | None = None,
    ) -> None:
        ts = now or utc_now()
        challenge.state = "delivery_failed"
        challenge.dispatch_finished_at = ts
        challenge.invalidated_at = ts
        challenge.dispatch_lease_owner = None
        challenge.dispatch_lease_until = None
        if clear_otp:
            challenge.code_digest = None
            challenge.code_salt = None
        await self._session.flush()

    async def list_stale_dispatching(
        self, *, older_than: datetime, limit: int = 20
    ) -> list[VerificationChallenge]:
        result = await self._session.execute(
            select(VerificationChallenge)
            .where(
                VerificationChallenge.state == "dispatching",
                VerificationChallenge.send_started_at.is_not(None),
                VerificationChallenge.send_started_at < older_than,
            )
            .order_by(VerificationChallenge.send_started_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Session issue / revoke
    # ------------------------------------------------------------------

    async def revoke_unrevoked_sessions(
        self,
        user_id: uuid.UUID,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> int:
        ts = now or utc_now()
        result = await self._session.execute(
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        sessions = list(result.scalars().all())
        for s in sessions:
            # ck_as_revoked_at requires revoked_at >= issued_at; concurrent
            # request clocks can otherwise set an earlier revoke timestamp.
            issued = s.issued_at
            if issued is not None and issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            revoke_at = ts
            if issued is not None and revoke_at < issued:
                revoke_at = issued
            s.revoked_at = revoke_at
            s.revocation_reason = reason
            if s.delete_after < revoke_at + SESSION_RETENTION:
                s.delete_after = revoke_at + SESSION_RETENTION
        if sessions:
            await self._session.flush()
        return len(sessions)

    async def insert_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        token_digest: bytes,
        token_key_version: int,
        role_snapshot: Any,
        created_request_id: str,
        now: datetime | None = None,
    ) -> AuthSession:
        ts = now or utc_now()
        expires = ts + SESSION_TTL
        row = AuthSession(
            id=session_id,
            user_id=user_id,
            token_digest=token_digest,
            token_key_version=token_key_version,
            role_snapshot=role_snapshot,
            issued_at=ts,
            expires_at=expires,
            revoked_at=None,
            revocation_reason=None,
            created_request_id=created_request_id[:128],
            delete_after=expires + SESSION_RETENTION,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_session_by_token_digest(
        self, *, token_key_version: int, token_digest: bytes
    ) -> AuthSession | None:
        result = await self._session.execute(
            select(AuthSession).where(
                AuthSession.token_key_version == token_key_version,
                AuthSession.token_digest == token_digest,
            )
        )
        return result.scalar_one_or_none()

    async def get_session_with_user_by_token_digest(
        self, *, token_key_version: int, token_digest: bytes
    ) -> tuple[AuthSession, User] | None:
        """Lookup exact session + owning user by token digest (no lock)."""
        result = await self._session.execute(
            select(AuthSession, User)
            .join(User, User.id == AuthSession.user_id)
            .where(
                AuthSession.token_key_version == token_key_version,
                AuthSession.token_digest == token_digest,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    async def lock_session_by_token_digest(
        self, *, token_key_version: int, token_digest: bytes
    ) -> AuthSession | None:
        """Lock the exact session row for revoke; does not touch other sessions."""
        result = await self._session.execute(
            select(AuthSession)
            .where(
                AuthSession.token_key_version == token_key_version,
                AuthSession.token_digest == token_digest,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def revoke_session(
        self,
        auth_session: AuthSession,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> bool:
        """Revoke one session if still unrevoked. Returns True when newly revoked."""
        ts = now or utc_now()
        if auth_session.revoked_at is not None:
            return False
        auth_session.revoked_at = ts
        auth_session.revocation_reason = reason
        if auth_session.delete_after < ts + SESSION_RETENTION:
            auth_session.delete_after = ts + SESSION_RETENTION
        await self._session.flush()
        return True

    # ------------------------------------------------------------------
    # Security audit
    # ------------------------------------------------------------------

    async def append_security_event(
        self,
        *,
        event_type: str,
        outcome: str,
        reason_code: str,
        request_id: str,
        user_id: uuid.UUID | None = None,
        challenge_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        subject_ref: bytes | None = None,
        safe_metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> AuthenticationSecurityEvent:
        ts = now or utc_now()
        event = AuthenticationSecurityEvent(
            id=uuid.uuid4(),
            event_type=event_type[:48],
            outcome=outcome[:32],
            reason_code=reason_code[:64],
            request_id=request_id[:128],
            user_id=user_id,
            challenge_id=challenge_id,
            session_id=session_id,
            subject_ref=subject_ref,
            safe_metadata=safe_metadata or {},
            occurred_at=ts,
            delete_after=ts + AUDIT_RETENTION,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def count_sessions_for_user(self, user_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        return len(list(result.scalars().all()))

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
