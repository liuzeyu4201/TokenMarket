"""Database constraint tests for authentication entities (T019)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.integration.conftest_authentication import AccountFactory, AuthPostgresHandle
from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _insert_idempotency(
    conn,  # type: ignore[no-untyped-def]
    *,
    key_digest: bytes,
    phone_ref: bytes,
    key_version: int = 1,
    state: str = "processing",
    http_status: int | None = None,
    result_code: str | None = None,
    completed_at: datetime | None = None,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    now = _utcnow()
    conn.execute(
        text(
            """
            INSERT INTO verification_request_idempotency_records (
                id, operation, key_digest, key_version, phone_ref, state,
                http_status, result_code, result_payload, created_at,
                completed_at, replay_until, delete_after
            ) VALUES (
                :id, 'request_verification_code', :key_digest, :key_version,
                :phone_ref, :state, :http_status, :result_code,
                CAST(:payload AS jsonb),
                :created_at, :completed_at, :replay_until, :delete_after
            )
            """
        ),
        {
            "id": row_id,
            "key_digest": key_digest,
            "key_version": key_version,
            "phone_ref": phone_ref,
            "state": state,
            "http_status": http_status,
            "result_code": result_code,
            "payload": None if state == "processing" else "{}",
            "created_at": now,
            "completed_at": completed_at,
            "replay_until": now + timedelta(seconds=60),
            "delete_after": now + timedelta(hours=22),
        },
    )
    return row_id


def _insert_challenge(
    conn,  # type: ignore[no-untyped-def]
    *,
    idempotency_id: uuid.UUID,
    phone_ref: bytes,
    user_id: uuid.UUID | None,
    state: str = "pending_delivery",
    send_started_at: datetime | None = None,
    dispatch_finished_at: datetime | None = None,
    delivered_at: datetime | None = None,
    consumed_at: datetime | None = None,
    attempt_count: int = 0,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    now = _utcnow()
    conn.execute(
        text(
            """
            INSERT INTO verification_challenges (
                id, user_id, idempotency_record_id, phone_ref,
                code_digest, code_salt, code_key_version, provider_request_ref,
                dispatch_lease_owner, dispatch_lease_until,
                send_started_at, dispatch_finished_at, attempt_count, state,
                created_at, delivered_at, expires_at, consumed_at,
                invalidated_at, delete_after
            ) VALUES (
                :id, :user_id, :idempotency_id, :phone_ref,
                :code_digest, :code_salt, 1, :provider_ref,
                NULL, NULL,
                :send_started_at, :dispatch_finished_at, :attempt_count, :state,
                :created_at, :delivered_at, :expires_at, :consumed_at,
                NULL, :delete_after
            )
            """
        ),
        {
            "id": row_id,
            "user_id": user_id,
            "idempotency_id": idempotency_id,
            "phone_ref": phone_ref,
            "code_digest": b"\xab" * 32 if state in ("pending_delivery", "delivered", "dispatching") else None,
            "code_salt": b"\xcd" * 16 if state in ("pending_delivery", "delivered", "dispatching") else None,
            "provider_ref": uuid.uuid4(),
            "send_started_at": send_started_at,
            "dispatch_finished_at": dispatch_finished_at,
            "attempt_count": attempt_count,
            "state": state,
            "created_at": now,
            "delivered_at": delivered_at,
            "expires_at": now + timedelta(minutes=5),
            "consumed_at": consumed_at,
            "delete_after": now + timedelta(minutes=5) + timedelta(hours=22),
        },
    )
    return row_id


def _insert_session(
    conn,  # type: ignore[no-untyped-def]
    *,
    user_id: uuid.UUID,
    token_digest: bytes,
    revoked_at: datetime | None = None,
    revocation_reason: str | None = None,
    token_key_version: int = 1,
    issued_at: datetime | None = None,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    now = issued_at or _utcnow()
    # Ensure revoked_at >= issued_at when both provided by caller with same clock.
    effective_revoked = revoked_at
    if effective_revoked is not None and effective_revoked < now:
        effective_revoked = now
    conn.execute(
        text(
            """
            INSERT INTO auth_sessions (
                id, user_id, token_digest, token_key_version, role_snapshot,
                issued_at, expires_at, revoked_at, revocation_reason,
                created_request_id, delete_after
            ) VALUES (
                :id, :user_id, :token_digest, :token_key_version, 'buyer',
                :issued_at, :expires_at, :revoked_at, :revocation_reason,
                :request_id, :delete_after
            )
            """
        ),
        {
            "id": row_id,
            "user_id": user_id,
            "token_digest": token_digest,
            "token_key_version": token_key_version,
            "issued_at": now,
            "expires_at": now + timedelta(minutes=60),
            "revoked_at": effective_revoked,
            "revocation_reason": revocation_reason,
            "request_id": f"req-{uuid.uuid4()}",
            "delete_after": now + timedelta(days=90),
        },
    )
    return row_id


@pytest.fixture
def constraint_engine(auth_postgres_container: AuthPostgresHandle):
    url = auth_postgres_container.database_url()
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    engine = create_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def factory(constraint_engine) -> AccountFactory:  # type: ignore[no-untyped-def]
    return AccountFactory(constraint_engine)


def test_idempotency_unique_operation_key_version_digest(constraint_engine) -> None:  # type: ignore[no-untyped-def]
    key = b"\x11" * 32
    phone = b"\x22" * 32
    with constraint_engine.begin() as conn:
        _insert_idempotency(conn, key_digest=key, phone_ref=phone)
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                _insert_idempotency(conn, key_digest=key, phone_ref=b"\x33" * 32)


def test_idempotency_processing_terminal_check(constraint_engine) -> None:  # type: ignore[no-untyped-def]
    with constraint_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                # processing must not have result fields
                row_id = uuid.uuid4()
                now = _utcnow()
                conn.execute(
                    text(
                        """
                        INSERT INTO verification_request_idempotency_records (
                            id, operation, key_digest, key_version, phone_ref, state,
                            http_status, result_code, created_at, completed_at,
                            replay_until, delete_after
                        ) VALUES (
                            :id, 'request_verification_code', :kd, 1, :pr,
                            'processing', 202, 'OK', :now, :now,
                            :replay, :delete_after
                        )
                        """
                    ),
                    {
                        "id": row_id,
                        "kd": b"\x44" * 32,
                        "pr": b"\x55" * 32,
                        "now": now,
                        "replay": now + timedelta(seconds=60),
                        "delete_after": now + timedelta(hours=22),
                    },
                )


def test_single_current_challenge_partial_unique(
    constraint_engine, factory: AccountFactory  # type: ignore[no-untyped-def]
) -> None:
    user = factory.create_active()
    phone_ref = b"\x66" * 32
    with constraint_engine.begin() as conn:
        id1 = _insert_idempotency(
            conn, key_digest=b"\x71" * 32, phone_ref=phone_ref
        )
        id2 = _insert_idempotency(
            conn, key_digest=b"\x72" * 32, phone_ref=phone_ref
        )
        _insert_challenge(
            conn,
            idempotency_id=id1,
            phone_ref=phone_ref,
            user_id=user.id,
            state="pending_delivery",
        )
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                _insert_challenge(
                    conn,
                    idempotency_id=id2,
                    phone_ref=phone_ref,
                    user_id=user.id,
                    state="delivered",
                    send_started_at=_utcnow(),
                    dispatch_finished_at=_utcnow(),
                    delivered_at=_utcnow(),
                )


def test_superseded_allows_new_current_challenge(
    constraint_engine, factory: AccountFactory  # type: ignore[no-untyped-def]
) -> None:
    user = factory.create_active()
    phone_ref = b"\x77" * 32
    with constraint_engine.begin() as conn:
        id1 = _insert_idempotency(
            conn, key_digest=b"\x81" * 32, phone_ref=phone_ref
        )
        id2 = _insert_idempotency(
            conn, key_digest=b"\x82" * 32, phone_ref=phone_ref
        )
        _insert_challenge(
            conn,
            idempotency_id=id1,
            phone_ref=phone_ref,
            user_id=user.id,
            state="superseded",
        )
        # new pending is allowed when old is superseded
        _insert_challenge(
            conn,
            idempotency_id=id2,
            phone_ref=phone_ref,
            user_id=user.id,
            state="pending_delivery",
        )


def test_send_started_state_check(constraint_engine, factory: AccountFactory) -> None:  # type: ignore[no-untyped-def]
    user = factory.create_active()
    phone_ref = b"\x88" * 32
    with constraint_engine.begin() as conn:
        idem = _insert_idempotency(
            conn, key_digest=b"\x91" * 32, phone_ref=phone_ref
        )
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                # pending_delivery cannot have send_started_at
                _insert_challenge(
                    conn,
                    idempotency_id=idem,
                    phone_ref=phone_ref,
                    user_id=user.id,
                    state="pending_delivery",
                    send_started_at=_utcnow(),
                )


def test_attempt_count_bounds(constraint_engine, factory: AccountFactory) -> None:  # type: ignore[no-untyped-def]
    user = factory.create_active()
    phone_ref = b"\x99" * 32
    with constraint_engine.begin() as conn:
        idem = _insert_idempotency(
            conn, key_digest=b"\xa1" * 32, phone_ref=phone_ref
        )
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                _insert_challenge(
                    conn,
                    idempotency_id=idem,
                    phone_ref=phone_ref,
                    user_id=user.id,
                    state="pending_delivery",
                    attempt_count=6,
                )


def test_single_active_session_partial_unique(
    constraint_engine, factory: AccountFactory  # type: ignore[no-untyped-def]
) -> None:
    user = factory.create_active()
    with constraint_engine.begin() as conn:
        _insert_session(conn, user_id=user.id, token_digest=b"\xb1" * 32)
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                _insert_session(conn, user_id=user.id, token_digest=b"\xb2" * 32)


def test_revoked_session_allows_new_active(
    constraint_engine, factory: AccountFactory  # type: ignore[no-untyped-def]
) -> None:
    user = factory.create_active()
    with constraint_engine.begin() as conn:
        # revoked_at must be >= issued_at (CHECK); use DB clock for both.
        now = conn.execute(text("SELECT NOW()")).scalar_one()
        _insert_session(
            conn,
            user_id=user.id,
            token_digest=b"\xc1" * 32,
            revoked_at=now + timedelta(seconds=1),
            revocation_reason="logout",
        )
        _insert_session(conn, user_id=user.id, token_digest=b"\xc2" * 32)


def test_session_token_digest_unique(
    constraint_engine, factory: AccountFactory  # type: ignore[no-untyped-def]
) -> None:
    u1 = factory.create_active()
    u2 = factory.create_active()
    digest = b"\xd1" * 32
    with constraint_engine.begin() as conn:
        _insert_session(conn, user_id=u1.id, token_digest=digest)
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                # revoke first so partial unique on user doesn't fire
                conn.execute(
                    text(
                        "UPDATE auth_sessions SET revoked_at = :now, "
                        "revocation_reason = 'logout' WHERE user_id = :uid"
                    ),
                    {"now": _utcnow(), "uid": u1.id},
                )
                _insert_session(conn, user_id=u2.id, token_digest=digest)


def test_session_revocation_consistency_check(
    constraint_engine, factory: AccountFactory  # type: ignore[no-untyped-def]
) -> None:
    user = factory.create_active()
    with constraint_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                _insert_session(
                    conn,
                    user_id=user.id,
                    token_digest=b"\xe1" * 32,
                    revoked_at=_utcnow(),
                    revocation_reason=None,
                )


def test_audit_on_delete_set_null(
    constraint_engine, factory: AccountFactory  # type: ignore[no-untyped-def]
) -> None:
    user = factory.create_active()
    phone_ref = b"\xf1" * 32
    now = _utcnow()
    with constraint_engine.begin() as conn:
        idem = _insert_idempotency(
            conn,
            key_digest=b"\xf2" * 32,
            phone_ref=phone_ref,
            state="succeeded",
            http_status=202,
            result_code="CHALLENGE_PENDING",
            completed_at=now,
        )
        # payload for terminal - need result_payload; helper sets {} for non-processing
        # but our insert used processing fields path when state=succeeded with completed
        # Re-check helper: for non-processing it sets payload to "{}". Good if JSON works.
        # Terminal consumed clears send_started (CHECK restricts it to dispatch states).
        challenge_id = _insert_challenge(
            conn,
            idempotency_id=idem,
            phone_ref=phone_ref,
            user_id=user.id,
            state="consumed",
            consumed_at=now,
        )
        session_id = _insert_session(
            conn, user_id=user.id, token_digest=b"\xf3" * 32
        )
        event_id = uuid.uuid4()
        conn.execute(
            text(
                """
                INSERT INTO authentication_security_events (
                    id, event_type, outcome, reason_code, request_id,
                    user_id, challenge_id, session_id, subject_ref,
                    safe_metadata, occurred_at, delete_after
                ) VALUES (
                    :id, 'session_issued', 'success', 'ok', :req,
                    :user_id, :challenge_id, :session_id, NULL,
                    '{}'::jsonb, :now, :delete_after
                )
                """
            ),
            {
                "id": event_id,
                "req": f"req-{uuid.uuid4()}",
                "user_id": user.id,
                "challenge_id": challenge_id,
                "session_id": session_id,
                "now": now,
                "delete_after": now + timedelta(days=180),
            },
        )

        # Delete session → session_id SET NULL
        conn.execute(
            text("DELETE FROM auth_sessions WHERE id = :id"),
            {"id": session_id},
        )
        row = conn.execute(
            text(
                "SELECT user_id, challenge_id, session_id "
                "FROM authentication_security_events WHERE id = :id"
            ),
            {"id": event_id},
        ).one()
        assert row.session_id is None
        assert row.user_id == user.id
        assert row.challenge_id == challenge_id

        # Delete challenge → challenge_id SET NULL
        conn.execute(
            text("DELETE FROM verification_challenges WHERE id = :id"),
            {"id": challenge_id},
        )
        row = conn.execute(
            text(
                "SELECT user_id, challenge_id, session_id "
                "FROM authentication_security_events WHERE id = :id"
            ),
            {"id": event_id},
        ).one()
        assert row.challenge_id is None
        assert row.user_id == user.id

        # Delete user → user_id SET NULL
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
        row = conn.execute(
            text(
                "SELECT user_id, challenge_id, session_id "
                "FROM authentication_security_events WHERE id = :id"
            ),
            {"id": event_id},
        ).one()
        assert row.user_id is None
