"""Auth backup → restore → invariant verification (004 T093 / T100).

Unit tests use synthetic rows only (no Docker). Optional live PostgreSQL path
runs when ``AUTH_BACKUP_TEST_DATABASE_URL`` is set *and* Docker is available.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from workflow.auth_backup_restore import (
    AUTH_TABLES,
    AuthBackupError,
    backup_from_rows,
    backup_restore_verify_memory,
    build_redacted_manifest,
    docker_available,
    document_pg_dump_command,
    isolated_database_url_from_env,
    redact_database_url,
    restore_logical_export_to_memory,
    verify_auth_invariants,
    verify_export_payload,
)


def _challenge(
    *,
    cid: str,
    state: str,
    send_started_at: str | None = None,
    consumed_at: str | None = None,
    code_digest: Any = None,
    user_id: str | None = "user-1",
) -> dict[str, Any]:
    return {
        "id": cid,
        "user_id": user_id,
        "state": state,
        "send_started_at": send_started_at,
        "consumed_at": consumed_at,
        "code_digest": code_digest,
    }


def _session(
    *,
    sid: str,
    user_id: str,
    revoked_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": sid,
        "user_id": user_id,
        "revoked_at": revoked_at,
    }


def test_redact_database_url_strips_password() -> None:
    url = "postgresql://app:tm_local_supersecretvalue_0123456789@127.0.0.1:5432/tokenmarket"
    redacted = redact_database_url(url)
    assert "supersecret" not in redacted
    assert "tm_local_" not in redacted or "[REDACTED]" in redacted
    assert "127.0.0.1" in redacted
    assert "tokenmarket" in redacted


def test_document_pg_dump_command_is_redacted() -> None:
    recipe = document_pg_dump_command(
        "postgresql://u:tm_local_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@127.0.0.1:5432/db",
        Path("/tmp/auth.dump"),
    )
    assert "pg_dump" in recipe
    assert "verification_challenges" in recipe
    assert "tm_local_aaa" not in recipe
    assert "[REDACTED]" in recipe


def test_verify_at_most_one_active_session_per_user() -> None:
    sessions = [
        _session(sid="s1", user_id="u1", revoked_at=None),
        _session(sid="s2", user_id="u1", revoked_at=None),
        _session(sid="s3", user_id="u2", revoked_at="2026-01-01T00:00:00+00:00"),
    ]
    report = verify_auth_invariants(sessions=sessions, challenges=[])
    assert report.ok is False
    assert any(v.code == "MULTIPLE_ACTIVE_SESSIONS" for v in report.violations)


def test_verify_single_active_session_ok() -> None:
    sessions = [
        _session(sid="s1", user_id="u1", revoked_at=None),
        _session(sid="s0", user_id="u1", revoked_at="2026-01-01T00:00:00+00:00"),
        _session(sid="s2", user_id="u2", revoked_at=None),
    ]
    report = verify_auth_invariants(sessions=sessions, challenges=[])
    assert report.ok is True
    assert report.violations == []


def test_verify_consumed_challenge_must_clear_digest_and_timestamp() -> None:
    bad = [
        _challenge(
            cid="c1",
            state="consumed",
            consumed_at=None,
            code_digest="deadbeef",
            send_started_at="2026-01-01T00:00:00+00:00",
        )
    ]
    report = verify_auth_invariants(challenges=bad, sessions=[])
    assert report.ok is False
    codes = {v.code for v in report.violations}
    assert "CONSUMED_MISSING_TIMESTAMP" in codes
    assert "CONSUMED_DIGEST_PRESENT" in codes


def test_verify_consumed_challenge_ok() -> None:
    ok_rows = [
        _challenge(
            cid="c1",
            state="consumed",
            consumed_at="2026-01-01T00:01:00+00:00",
            code_digest=None,
            send_started_at="2026-01-01T00:00:00+00:00",
        )
    ]
    report = verify_auth_invariants(challenges=ok_rows, sessions=[])
    assert report.ok is True


def test_verify_send_started_not_resend_eligible() -> None:
    bad = [
        _challenge(
            cid="c-dispatch",
            state="pending_delivery",
            send_started_at="2026-01-01T00:00:00+00:00",
        )
    ]
    report = verify_auth_invariants(challenges=bad, sessions=[])
    assert report.ok is False
    assert any(v.code == "SEND_STARTED_RESEND_ELIGIBLE" for v in report.violations)


def test_verify_send_started_dispatching_ok() -> None:
    ok_rows = [
        _challenge(
            cid="c-d",
            state="dispatching",
            send_started_at="2026-01-01T00:00:00+00:00",
        ),
        _challenge(
            cid="c-pending",
            state="pending_delivery",
            send_started_at=None,
        ),
    ]
    report = verify_auth_invariants(challenges=ok_rows, sessions=[])
    assert report.ok is True


def test_backup_from_rows_writes_redacted_manifest(tmp_path: Path) -> None:
    challenges = [
        _challenge(
            cid="c1",
            state="consumed",
            consumed_at="2026-01-01T00:01:00+00:00",
            send_started_at="2026-01-01T00:00:00+00:00",
        ),
        _challenge(
            cid="c2",
            state="dispatching",
            send_started_at="2026-01-01T00:00:30+00:00",
        ),
    ]
    sessions = [
        _session(sid="s1", user_id="u1", revoked_at=None),
        _session(sid="s0", user_id="u1", revoked_at="2026-01-01T00:00:00+00:00"),
    ]
    artifact = backup_from_rows(
        output_dir=tmp_path / "bak",
        challenges=challenges,
        sessions=sessions,
        source_url_redacted="postgresql://app:[REDACTED]@127.0.0.1:5432/iso",
    )
    assert artifact.export_path.is_file()
    assert artifact.manifest_path.is_file()
    manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    assert manifest["kind"] == "tokenmarket.auth_backup_manifest"
    assert set(manifest["tables"]) == set(AUTH_TABLES)
    assert manifest["tables"]["verification_challenges"]["row_count"] == 2
    assert manifest["tables"]["auth_sessions"]["row_count"] == 2
    text = artifact.manifest_path.read_text(encoding="utf-8")
    assert "password" not in text.lower() or "[REDACTED]" in text
    assert "otp" not in text.lower()


def test_backup_from_rows_rejects_invalid_source(tmp_path: Path) -> None:
    with pytest.raises(AuthBackupError) as exc:
        backup_from_rows(
            output_dir=tmp_path,
            challenges=[
                _challenge(
                    cid="c1",
                    state="pending_delivery",
                    send_started_at="2026-01-01T00:00:00+00:00",
                )
            ],
            sessions=[],
        )
    assert exc.value.code == "INVARIANT_VIOLATION"


def test_memory_backup_restore_roundtrip(tmp_path: Path) -> None:
    challenges = [
        _challenge(
            cid="c-consumed",
            state="consumed",
            consumed_at="2026-01-01T00:02:00+00:00",
            send_started_at="2026-01-01T00:00:00+00:00",
            code_digest=None,
        ),
        _challenge(
            cid="c-send-started",
            state="dispatching",
            send_started_at="2026-01-01T00:01:00+00:00",
        ),
        _challenge(cid="c-pending", state="pending_delivery"),
    ]
    sessions = [
        _session(sid="active", user_id="u1", revoked_at=None),
        _session(sid="revoked", user_id="u1", revoked_at="2026-01-01T00:00:00+00:00"),
    ]
    result = backup_restore_verify_memory(
        challenges=challenges,
        sessions=sessions,
        work_dir=tmp_path / "roundtrip",
    )
    assert result["ok"] is True
    restored = restore_logical_export_to_memory(Path(result["export_path"]))
    # Consumed stays consumed; revoked stays revoked; single active session.
    by_id = {r["id"]: r for r in restored["verification_challenges"]}
    assert by_id["c-consumed"]["state"] == "consumed"
    assert by_id["c-consumed"]["consumed_at"]
    assert by_id["c-send-started"]["state"] == "dispatching"
    assert by_id["c-send-started"]["send_started_at"]
    assert by_id["c-send-started"]["state"] != "pending_delivery"
    sessions_by_id = {r["id"]: r for r in restored["auth_sessions"]}
    assert sessions_by_id["revoked"]["revoked_at"]
    assert sessions_by_id["active"]["revoked_at"] is None
    report = verify_auth_invariants(
        challenges=restored["verification_challenges"],
        sessions=restored["auth_sessions"],
    )
    assert report.ok is True


def test_build_redacted_manifest_truncates_opaque_ids() -> None:
    stats = {
        "auth_sessions": {
            "row_count": 250,
            "opaque_ids": [f"id-{i}" for i in range(250)],
        }
    }
    manifest = build_redacted_manifest(table_stats=stats)
    assert manifest.tables["auth_sessions"]["row_count"] == 250
    assert len(manifest.tables["auth_sessions"]["opaque_ids"]) == 200
    assert manifest.tables["auth_sessions"]["opaque_ids_truncated"] is True


def test_verify_export_payload_wrapper() -> None:
    payload = {
        "tables": {
            "verification_challenges": [
                _challenge(
                    cid="c1",
                    state="consumed",
                    consumed_at="2026-01-01T00:00:00+00:00",
                    send_started_at="2026-01-01T00:00:00+00:00",
                )
            ],
            "auth_sessions": [_session(sid="s1", user_id="u1")],
        }
    }
    assert verify_export_payload(payload).ok is True


@pytest.mark.skipif(
    not isolated_database_url_from_env() or not docker_available(),
    reason="optional live PG: set AUTH_BACKUP_TEST_DATABASE_URL and require Docker",
)
def test_optional_live_backup_restore_when_configured(tmp_path: Path) -> None:
    """Optional real PostgreSQL path — skipped unless explicitly configured.

    Operators wire an *isolated* DATABASE_URL with auth schema applied. This
    suite never starts containers itself to keep offline CI deterministic.
    """
    from workflow.auth_backup_restore import backup_database

    url = isolated_database_url_from_env()
    assert url
    # Backup against the isolated source; restore into the same URL is forbidden
    # so we only exercise backup + invariant side here when a single URL is set.
    artifact = backup_database(url, tmp_path / "live", prefer_pg_dump=True)
    assert artifact.export_path.exists() or (tmp_path / "live" / "auth_tables.json").exists()
    assert artifact.manifest_path.is_file()
    manifest_text = artifact.manifest_path.read_text(encoding="utf-8")
    assert "://" in manifest_text  # redacted source may remain
    assert "[REDACTED]" in manifest_text or "password" not in manifest_text.lower()
