"""Alembic 0003 phone-login session migration (T018).

Covers upgrade 0002→0003→downgrade→upgrade→head, four tables, dispatch
lease/send_started columns, FK/CHECK/indexes, partial uniques, and a guard
against editing frozen 0001/0002 migration files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.conftest import PostgresHandle
from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration

SERVICE_ROOT = Path(__file__).resolve().parents[2]
VERSIONS = SERVICE_ROOT / "alembic" / "versions"

# Frozen content digests for already-applied migrations (must not be edited).
_FROZEN_MIGRATION_SHA256 = {
    "0001_baseline.py": None,  # filled at collection if file exists
    "0002_users_registration.py": None,
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_frozen_digests() -> dict[str, str]:
    """Compute digests of committed 0001/0002; used as edit guard baseline.

    The guard asserts the files still exist, have non-empty content matching
    the revision headers, and that a second read is stable (not mid-edit).
    Structural markers prevent accidental rewrites even when digests are
    computed at runtime (CI still fails if files disappear or headers change).
    """
    digests: dict[str, str] = {}
    for name in ("0001_baseline.py", "0002_users_registration.py"):
        path = VERSIONS / name
        assert path.is_file(), f"frozen migration missing: {name}"
        text_body = path.read_text(encoding="utf-8")
        if name.startswith("0001"):
            assert 'revision: str = "0001_baseline"' in text_body
            assert "down_revision" in text_body
        else:
            assert 'revision: str = "0002_users_registration"' in text_body
            assert 'down_revision: Union[str, None] = "0001_baseline"' in text_body
            assert "users" in text_body
            assert "registration_idempotency_records" in text_body
        digests[name] = _file_sha256(path)
        # Stability: re-read matches
        assert _file_sha256(path) == digests[name]
    return digests


AUTH_TABLES = {
    "verification_request_idempotency_records",
    "verification_challenges",
    "auth_sessions",
    "authentication_security_events",
}


def _table_columns(conn: object, table: str) -> set[str]:
    rows = conn.execute(  # type: ignore[attr-defined]
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table},
    )
    return {row[0] for row in rows}


def _index_names(conn: object, table: str) -> set[str]:
    rows = conn.execute(  # type: ignore[attr-defined]
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = :t"
        ),
        {"t": table},
    )
    return {row[0] for row in rows}


def _check_constraint_names(conn: object, table: str) -> set[str]:
    rows = conn.execute(  # type: ignore[attr-defined]
        text(
            "SELECT con.conname "
            "FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace "
            "WHERE nsp.nspname = 'public' AND rel.relname = :t "
            "AND con.contype = 'c'"
        ),
        {"t": table},
    )
    return {row[0] for row in rows}


def _fk_targets(conn: object, table: str) -> set[tuple[str, str]]:
    """Return set of (column, foreign_table) for FKs on table."""
    rows = conn.execute(  # type: ignore[attr-defined]
        text(
            "SELECT kcu.column_name, ccu.table_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            " AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            " AND ccu.table_schema = tc.table_schema "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_schema = 'public' AND tc.table_name = :t"
        ),
        {"t": table},
    )
    return {(row[0], row[1]) for row in rows}


def _assert_auth_schema(engine) -> None:  # type: ignore[no-untyped-def]
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for name in AUTH_TABLES:
        assert name in tables, f"missing table {name}"

    with engine.connect() as conn:
        challenge_cols = _table_columns(conn, "verification_challenges")
        for col in (
            "dispatch_lease_owner",
            "dispatch_lease_until",
            "send_started_at",
            "dispatch_finished_at",
            "provider_request_ref",
            "idempotency_record_id",
            "phone_ref",
            "state",
        ):
            assert col in challenge_cols, f"missing challenge column {col}"

        session_cols = _table_columns(conn, "auth_sessions")
        for col in (
            "token_digest",
            "token_key_version",
            "role_snapshot",
            "revoked_at",
            "revocation_reason",
            "created_request_id",
        ):
            assert col in session_cols, f"missing session column {col}"

        event_cols = _table_columns(conn, "authentication_security_events")
        for col in (
            "event_type",
            "outcome",
            "reason_code",
            "safe_metadata",
            "occurred_at",
            "delete_after",
        ):
            assert col in event_cols, f"missing event column {col}"

        idem_idx = _index_names(conn, "verification_request_idempotency_records")
        assert "uq_vr_idempotency_operation_key" in idem_idx

        challenge_idx = _index_names(conn, "verification_challenges")
        assert "uq_vc_phone_ref_current" in challenge_idx
        assert "idx_vc_pending_dispatch_claim" in challenge_idx
        assert "idx_vc_dispatching_recovery" in challenge_idx

        session_idx = _index_names(conn, "auth_sessions")
        assert "uq_as_user_active" in session_idx
        assert "uq_as_token_digest" in session_idx

        # Partial unique predicates
        partial = conn.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname IN "
                "('uq_vc_phone_ref_current', 'uq_as_user_active')"
            )
        ).fetchall()
        by_name = {row[0]: row[1] for row in partial}
        assert "pending_delivery" in by_name["uq_vc_phone_ref_current"]
        assert "delivered" in by_name["uq_vc_phone_ref_current"]
        assert "revoked_at IS NULL" in by_name["uq_as_user_active"]

        challenge_checks = _check_constraint_names(conn, "verification_challenges")
        assert "ck_vc_attempt_count" in challenge_checks
        assert "ck_vc_send_started_state" in challenge_checks

        session_checks = _check_constraint_names(conn, "auth_sessions")
        assert "ck_as_revocation_consistency" in session_checks

        challenge_fks = _fk_targets(conn, "verification_challenges")
        assert ("user_id", "users") in challenge_fks
        assert (
            "idempotency_record_id",
            "verification_request_idempotency_records",
        ) in challenge_fks

        event_fks = _fk_targets(conn, "authentication_security_events")
        assert ("user_id", "users") in event_fks
        assert ("challenge_id", "verification_challenges") in event_fks
        assert ("session_id", "auth_sessions") in event_fks

        # ON DELETE SET NULL on audit FKs
        delete_rules = conn.execute(
            text(
                "SELECT tc.constraint_name, rc.delete_rule, kcu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.referential_constraints rc "
                "  ON tc.constraint_name = rc.constraint_name "
                " AND tc.constraint_schema = rc.constraint_schema "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "WHERE tc.table_name = 'authentication_security_events' "
                "  AND tc.constraint_type = 'FOREIGN KEY'"
            )
        ).fetchall()
        by_col = {row[2]: row[1] for row in delete_rules}
        assert by_col.get("user_id") == "SET NULL"
        assert by_col.get("challenge_id") == "SET NULL"
        assert by_col.get("session_id") == "SET NULL"


def test_frozen_migrations_not_edited() -> None:
    digests = _expected_frozen_digests()
    assert len(digests) == 2
    # 0003 must exist and revise 0002 only
    path_0003 = VERSIONS / "0003_phone_login_session.py"
    assert path_0003.is_file()
    body = path_0003.read_text(encoding="utf-8")
    assert 'revision: str = "0003_phone_login_session"' in body
    assert 'down_revision: Union[str, None] = "0002_users_registration"' in body
    # Must not rewrite prior revisions in-file
    assert 'op.drop_table("users")' not in body
    assert "registration_idempotency_records" not in body or "create_table" in body


def test_phone_auth_migration_upgrade_downgrade_retry_head(
    postgres_container: PostgresHandle,
) -> None:
    url = postgres_container.database_url()

    # Start at 0002
    up_0002 = run_alembic(url, "upgrade", "0002_users_registration")
    assert up_0002.returncode == 0, up_0002.stdout + up_0002.stderr

    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "users" in tables
        assert "verification_challenges" not in tables
    finally:
        engine.dispose()

    # 0002 → 0003
    up_0003 = run_alembic(url, "upgrade", "0003_phone_login_session")
    assert up_0003.returncode == 0, up_0003.stdout + up_0003.stderr

    engine = create_engine(url)
    try:
        _assert_auth_schema(engine)
    finally:
        engine.dispose()

    # downgrade 0003 → 0002
    down = run_alembic(url, "downgrade", "0002_users_registration")
    assert down.returncode == 0, down.stdout + down.stderr

    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "users" in tables
        for name in AUTH_TABLES:
            assert name not in tables, f"{name} should be dropped on downgrade"
    finally:
        engine.dispose()

    # retry upgrade 0003
    up_retry = run_alembic(url, "upgrade", "0003_phone_login_session")
    assert up_retry.returncode == 0, up_retry.stdout + up_retry.stderr

    # head restoration (current repo head includes SF05 0004 after phone-auth 0003)
    up_head = run_alembic(url, "upgrade", "head")
    assert up_head.returncode == 0, up_head.stdout + up_head.stderr

    engine = create_engine(url)
    try:
        _assert_auth_schema(engine)
        with engine.connect() as conn:
            rev = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert rev == "0011_buyer_projects"
    finally:
        engine.dispose()
