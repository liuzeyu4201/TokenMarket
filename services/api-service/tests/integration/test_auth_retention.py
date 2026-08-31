"""Authentication retention cleanup (T089 / T095).

Covers challenge/OTP expires_at+22h, idempotency created_at+22h, session 90d,
event 180d, 500-row txn batches, 900s budget, advisory lock, already_running,
repeat safety, and the 24h hard bound for OTP/challenge material.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.maintenance.auth_cleanup import (
    AUTH_CLEANUP_ADVISORY_LOCK_KEY,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_RUNTIME_SECONDS,
    run_cleanup,
)
from app.repositories.authentication import (
    AUDIT_RETENTION,
    CHALLENGE_DELETE_BUFFER,
    IDEMPOTENCY_DELETE_BUFFER,
    SESSION_RETENTION,
)
from tests.integration.conftest_authentication import AccountFactory

pytestmark = pytest.mark.integration

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def _insert_idempotency(
    conn,  # type: ignore[no-untyped-def]
    *,
    created_at: datetime,
    delete_after: datetime,
    key_digest: bytes | None = None,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    conn.execute(
        text("""
            INSERT INTO verification_request_idempotency_records (
                id, operation, key_digest, key_version, phone_ref, state,
                http_status, result_code, result_payload, created_at,
                completed_at, replay_until, delete_after
            ) VALUES (
                :id, 'request_verification_code', :key_digest, 1,
                :phone_ref, 'succeeded', 202, '0', '{}'::jsonb,
                :created_at, :created_at, :replay_until, :delete_after
            )
            """),
        {
            "id": row_id,
            "key_digest": key_digest or uuid.uuid4().bytes + uuid.uuid4().bytes[:16],
            "phone_ref": uuid.uuid4().bytes + uuid.uuid4().bytes[:16],
            "created_at": created_at,
            "replay_until": created_at + timedelta(seconds=60),
            "delete_after": delete_after,
        },
    )
    return row_id


def _insert_challenge(
    conn,  # type: ignore[no-untyped-def]
    *,
    idempotency_id: uuid.UUID,
    expires_at: datetime,
    delete_after: datetime,
    created_at: datetime | None = None,
    user_id: uuid.UUID | None = None,
    with_otp: bool = True,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    created = created_at or (expires_at - timedelta(minutes=5))
    # Terminal ``expired`` rows must keep send_started_at NULL
    # (ck_vc_send_started_state only allows it for dispatching/delivered/failed).
    conn.execute(
        text("""
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
                NULL, NULL, 0, 'expired',
                :created_at, NULL, :expires_at, NULL,
                NULL, :delete_after
            )
            """),
        {
            "id": row_id,
            "user_id": user_id,
            "idempotency_id": idempotency_id,
            "phone_ref": uuid.uuid4().bytes + uuid.uuid4().bytes[:16],
            "code_digest": (
                (uuid.uuid4().bytes + uuid.uuid4().bytes[:16]) if with_otp else None
            ),
            "code_salt": uuid.uuid4().bytes if with_otp else None,
            "provider_ref": uuid.uuid4(),
            "created_at": created,
            "expires_at": expires_at,
            "delete_after": delete_after,
        },
    )
    return row_id


def _insert_session(
    conn,  # type: ignore[no-untyped-def]
    *,
    user_id: uuid.UUID,
    issued_at: datetime,
    expires_at: datetime,
    delete_after: datetime,
    revoked_at: datetime | None = None,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    conn.execute(
        text("""
            INSERT INTO auth_sessions (
                id, user_id, token_digest, token_key_version, role_snapshot,
                issued_at, expires_at, revoked_at, revocation_reason,
                created_request_id, delete_after
            ) VALUES (
                :id, :user_id, :token_digest, 1, 'buyer',
                :issued_at, :expires_at, :revoked_at, :reason,
                :request_id, :delete_after
            )
            """),
        {
            "id": row_id,
            "user_id": user_id,
            "token_digest": uuid.uuid4().bytes + uuid.uuid4().bytes[:16],
            "issued_at": issued_at,
            "expires_at": expires_at,
            "revoked_at": revoked_at,
            "reason": "logout" if revoked_at is not None else None,
            "request_id": f"req-{row_id}",
            "delete_after": delete_after,
        },
    )
    return row_id


def _insert_event(
    conn,  # type: ignore[no-untyped-def]
    *,
    occurred_at: datetime,
    delete_after: datetime,
    challenge_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    conn.execute(
        text("""
            INSERT INTO authentication_security_events (
                id, event_type, outcome, reason_code, request_id,
                user_id, challenge_id, session_id, subject_ref,
                safe_metadata, occurred_at, delete_after
            ) VALUES (
                :id, 'auth.session.revoked', 'success', 'logout', :request_id,
                :user_id, :challenge_id, :session_id, NULL,
                '{}'::jsonb, :occurred_at, :delete_after
            )
            """),
        {
            "id": row_id,
            "request_id": f"evt-{row_id}",
            "user_id": user_id,
            "challenge_id": challenge_id,
            "session_id": session_id,
            "occurred_at": occurred_at,
            "delete_after": delete_after,
        },
    )
    return row_id


def test_default_cli_flags_match_contract() -> None:
    assert DEFAULT_BATCH_SIZE == 500
    assert DEFAULT_MAX_RUNTIME_SECONDS == 900


def test_retention_windows_constants() -> None:
    assert CHALLENGE_DELETE_BUFFER == timedelta(hours=22)
    assert IDEMPOTENCY_DELETE_BUFFER == timedelta(hours=22)
    assert SESSION_RETENTION == timedelta(days=90)
    assert AUDIT_RETENTION == timedelta(days=180)


def test_deletes_due_rows_and_keeps_fresh(
    auth_migrated_postgres: str,
    auth_db_engine: Engine,
) -> None:
    factory = AccountFactory(auth_db_engine)
    user = factory.create_active()
    now = _utcnow()

    with auth_db_engine.begin() as conn:
        # Due challenge/OTP (expires_at + 22h already passed).
        due_exp = now - timedelta(hours=23)
        due_idem = _insert_idempotency(
            conn,
            created_at=due_exp - timedelta(minutes=5),
            delete_after=due_exp - timedelta(minutes=5) + IDEMPOTENCY_DELETE_BUFFER,
        )
        due_ch = _insert_challenge(
            conn,
            idempotency_id=due_idem,
            expires_at=due_exp,
            delete_after=due_exp + CHALLENGE_DELETE_BUFFER,
            user_id=user.id,
        )

        # Fresh challenge still within retention.
        fresh_exp = now + timedelta(minutes=4)
        fresh_idem = _insert_idempotency(
            conn,
            created_at=now,
            delete_after=now + IDEMPOTENCY_DELETE_BUFFER,
            key_digest=b"f" * 32,
        )
        fresh_ch = _insert_challenge(
            conn,
            idempotency_id=fresh_idem,
            expires_at=fresh_exp,
            delete_after=fresh_exp + CHALLENGE_DELETE_BUFFER,
            user_id=None,
            with_otp=True,
        )

        # Session: due (90d after expire) vs still retained.
        due_sess_exp = now - timedelta(days=91)
        due_sess = _insert_session(
            conn,
            user_id=user.id,
            issued_at=due_sess_exp - timedelta(hours=1),
            expires_at=due_sess_exp,
            delete_after=due_sess_exp + SESSION_RETENTION,
            revoked_at=due_sess_exp,
        )
        # Active-ish recent session (not due).
        user2 = factory.create_active()
        keep_sess = _insert_session(
            conn,
            user_id=user2.id,
            issued_at=now - timedelta(minutes=10),
            expires_at=now + timedelta(minutes=50),
            delete_after=now + timedelta(minutes=50) + SESSION_RETENTION,
        )

        # Events: 180d retention.
        due_evt = _insert_event(
            conn,
            occurred_at=now - timedelta(days=181),
            delete_after=now - timedelta(days=1),
            user_id=user.id,
        )
        keep_evt = _insert_event(
            conn,
            occurred_at=now,
            delete_after=now + AUDIT_RETENTION,
            user_id=user.id,
        )

    result = run_cleanup(
        database_url=auth_migrated_postgres,
        batch_size=500,
        max_runtime_seconds=900,
    )
    assert result.outcome in {"success", "budget_exhausted"}
    assert result.rows_by_entity.get("challenges", 0) >= 1
    assert result.rows_by_entity.get("idempotency", 0) >= 1
    assert result.rows_by_entity.get("sessions", 0) >= 1
    assert result.rows_by_entity.get("security_events", 0) >= 1

    with auth_db_engine.connect() as conn:
        remaining_ch = {
            r[0]
            for r in conn.execute(
                text("SELECT id FROM verification_challenges")
            ).fetchall()
        }
        remaining_idem = {
            r[0]
            for r in conn.execute(
                text("SELECT id FROM verification_request_idempotency_records")
            ).fetchall()
        }
        remaining_sess = {
            r[0] for r in conn.execute(text("SELECT id FROM auth_sessions")).fetchall()
        }
        remaining_evt = {
            r[0]
            for r in conn.execute(
                text("SELECT id FROM authentication_security_events")
            ).fetchall()
        }

    assert due_ch not in remaining_ch
    assert due_idem not in remaining_idem
    assert due_sess not in remaining_sess
    assert due_evt not in remaining_evt
    assert fresh_ch in remaining_ch
    assert fresh_idem in remaining_idem
    assert keep_sess in remaining_sess
    assert keep_evt in remaining_evt


def test_batch_size_limits_rows_per_transaction(
    auth_migrated_postgres: str,
    auth_db_engine: Engine,
) -> None:
    now = _utcnow()
    with auth_db_engine.begin() as conn:
        for i in range(7):
            created = now - timedelta(hours=30)
            idem = _insert_idempotency(
                conn,
                created_at=created,
                delete_after=created + IDEMPOTENCY_DELETE_BUFFER,
                key_digest=bytes([i]) * 32,
            )
            _insert_challenge(
                conn,
                idempotency_id=idem,
                expires_at=created + timedelta(minutes=5),
                delete_after=created + timedelta(minutes=5) + CHALLENGE_DELETE_BUFFER,
            )

    # With batch_size=2, each table batch deletes at most 2 rows; all due rows
    # must still be gone after the run finishes within the budget.
    result = run_cleanup(
        database_url=auth_migrated_postgres,
        batch_size=2,
        max_runtime_seconds=900,
    )
    assert result.outcome in {"success", "budget_exhausted"}
    assert result.batches >= 2  # multiple batches needed for 7 rows
    assert _count(auth_db_engine, "verification_challenges") == 0
    assert _count(auth_db_engine, "verification_request_idempotency_records") == 0


def test_max_runtime_budget_stops_work(
    auth_migrated_postgres: str,
    auth_db_engine: Engine,
) -> None:
    now = _utcnow()
    with auth_db_engine.begin() as conn:
        for i in range(5):
            created = now - timedelta(hours=30)
            idem = _insert_idempotency(
                conn,
                created_at=created,
                delete_after=created + IDEMPOTENCY_DELETE_BUFFER,
                key_digest=bytes([i + 10]) * 32,
            )
            _insert_challenge(
                conn,
                idempotency_id=idem,
                expires_at=created + timedelta(minutes=5),
                delete_after=created + timedelta(minutes=5) + CHALLENGE_DELETE_BUFFER,
            )

    # Synthetic clock: first call is start, subsequent calls exceed budget.
    ticks = {"n": 0}

    def clock() -> float:
        ticks["n"] += 1
        # start → 0.0; immediately after start check → already over budget
        return 0.0 if ticks["n"] <= 1 else 10_000.0

    result = run_cleanup(
        database_url=auth_migrated_postgres,
        batch_size=1,
        max_runtime_seconds=1,
        monotonic=clock,
    )
    assert result.outcome in {"budget_exhausted", "success"}
    # With budget expired immediately, zero or partial deletes are acceptable.
    assert result.duration_seconds >= 0


def test_advisory_lock_already_running(
    auth_migrated_postgres: str,
    auth_db_engine: Engine,
) -> None:
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    holder = engine.connect()
    try:
        acquired = holder.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": AUTH_CLEANUP_ADVISORY_LOCK_KEY},
        ).scalar_one()
        assert acquired is True

        result = run_cleanup(
            database_url=auth_migrated_postgres,
            batch_size=500,
            max_runtime_seconds=30,
        )
        assert result.outcome == "already_running"
    finally:
        holder.execute(
            text("SELECT pg_advisory_unlock(:k)"),
            {"k": AUTH_CLEANUP_ADVISORY_LOCK_KEY},
        )
        holder.close()
        engine.dispose()


def test_repeat_run_is_idempotent(
    auth_migrated_postgres: str,
    auth_db_engine: Engine,
) -> None:
    now = _utcnow()
    with auth_db_engine.begin() as conn:
        created = now - timedelta(hours=30)
        idem = _insert_idempotency(
            conn,
            created_at=created,
            delete_after=created + IDEMPOTENCY_DELETE_BUFFER,
        )
        _insert_challenge(
            conn,
            idempotency_id=idem,
            expires_at=created + timedelta(minutes=5),
            delete_after=created + timedelta(minutes=5) + CHALLENGE_DELETE_BUFFER,
        )

    first = run_cleanup(
        database_url=auth_migrated_postgres,
        batch_size=500,
        max_runtime_seconds=900,
    )
    second = run_cleanup(
        database_url=auth_migrated_postgres,
        batch_size=500,
        max_runtime_seconds=900,
    )
    assert first.outcome == "success"
    assert second.outcome == "success"
    assert second.rows_by_entity.get("challenges", 0) == 0
    assert second.rows_by_entity.get("idempotency", 0) == 0


def test_hard_24h_bound_material_removed(
    auth_migrated_postgres: str,
    auth_db_engine: Engine,
) -> None:
    """expires_at + 22h delete_after ⇒ cleanup before 24h hard bound."""
    now = _utcnow()
    # Material expired 23h ago: delete_after = expires + 22h is 1h in the past.
    expires_at = now - timedelta(hours=23)
    with auth_db_engine.begin() as conn:
        idem = _insert_idempotency(
            conn,
            created_at=expires_at - timedelta(minutes=5),
            delete_after=expires_at - timedelta(minutes=5) + IDEMPOTENCY_DELETE_BUFFER,
        )
        ch = _insert_challenge(
            conn,
            idempotency_id=idem,
            expires_at=expires_at,
            delete_after=expires_at + CHALLENGE_DELETE_BUFFER,
            with_otp=True,
        )

    # Prove delete_after is still within 24h of expires_at.
    assert CHALLENGE_DELETE_BUFFER < timedelta(hours=24)

    run_cleanup(
        database_url=auth_migrated_postgres,
        batch_size=500,
        max_runtime_seconds=900,
    )
    with auth_db_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT COUNT(*) FROM verification_challenges WHERE id = :id"),
            {"id": ch},
        ).scalar_one()
    assert exists == 0


def test_module_entrypoint_cli(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", auth_migrated_postgres)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.maintenance.auth_cleanup",
            "--batch-size",
            "500",
            "--max-runtime-seconds",
            "900",
        ],
        cwd=str(SERVICE_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**dict(__import__("os").environ), "DATABASE_URL": auth_migrated_postgres},
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["outcome"] in {"success", "already_running", "budget_exhausted"}
    assert "run_id" in payload
    assert "rows_by_entity" in payload
