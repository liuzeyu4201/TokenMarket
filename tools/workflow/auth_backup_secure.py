"""Fail-closed identifier allowlisting, exclusive file creation, and at-rest encryption."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

def _error(code: str, message: str) -> Exception:
    from .auth_backup_restore import AuthBackupError

    return AuthBackupError(code, message)


def _tables() -> tuple[str, ...]:
    from .auth_backup_restore import AUTH_TABLES

    return AUTH_TABLES

SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FORBIDDEN_FRAGMENTS = ('"', "'", ";", "--", "/*", "*/", " ", "\t", "\n")

AUTH_TABLE_COLUMNS: dict[str, frozenset[str]] = {
    "verification_request_idempotency_records": frozenset(
        {
            "id",
            "operation",
            "key_digest",
            "key_version",
            "phone_ref",
            "state",
            "http_status",
            "result_code",
            "result_payload",
            "created_at",
            "completed_at",
            "replay_until",
            "delete_after",
        }
    ),
    "verification_challenges": frozenset(
        {
            "id",
            "user_id",
            "idempotency_record_id",
            "phone_ref",
            "code_digest",
            "code_salt",
            "code_key_version",
            "provider_request_ref",
            "dispatch_lease_owner",
            "dispatch_lease_until",
            "send_started_at",
            "dispatch_finished_at",
            "attempt_count",
            "state",
            "created_at",
            "delivered_at",
            "expires_at",
            "consumed_at",
            "invalidated_at",
            "delete_after",
        }
    ),
    "auth_sessions": frozenset(
        {
            "id",
            "user_id",
            "token_digest",
            "token_key_version",
            "role_snapshot",
            "issued_at",
            "expires_at",
            "revoked_at",
            "revocation_reason",
            "created_request_id",
            "delete_after",
        }
    ),
    "authentication_security_events": frozenset(
        {
            "id",
            "event_type",
            "outcome",
            "reason_code",
            "request_id",
            "user_id",
            "challenge_id",
            "session_id",
            "subject_ref",
            "safe_metadata",
            "occurred_at",
            "delete_after",
        }
    ),
}


def validate_identifier(key: str) -> str:
    if not isinstance(key, str) or not key:
        raise _error("INVALID_IDENTIFIER", "column name must be a non-empty string")
    if not SAFE_IDENT_RE.fullmatch(key):
        raise _error(
            "INVALID_IDENTIFIER",
            "JSON object keys containing quotes or SQL fragments are rejected",
        )
    lowered = key.lower()
    if any(frag in key or frag in lowered for frag in FORBIDDEN_FRAGMENTS):
        raise _error(
            "INVALID_IDENTIFIER",
            "JSON object keys containing quotes or SQL fragments are rejected",
        )
    return key


def validate_restore_tables(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    require_known_table: bool = True,
) -> None:
    for table, rows in tables.items():
        if require_known_table and table not in _tables():
            raise _error("UNKNOWN_TABLE", f"table {table!r} is not allowlisted")
        allowed = AUTH_TABLE_COLUMNS.get(table, frozenset())
        for row in rows:
            if not isinstance(row, Mapping):
                raise _error("BACKUP_INVALID", "row must be an object")
            for key in row.keys():
                ident = validate_identifier(str(key))
                if allowed and ident not in allowed:
                    raise _error(
                        "UNKNOWN_COLUMN",
                        f"column {ident!r} is not allowlisted for {table}",
                    )


def quote_ident(name: str) -> str:
    ident = validate_identifier(name)
    return '"' + ident.replace('"', "") + '"'


def backup_encryption_key(raw: str | None = None) -> bytes:
    text = (raw if raw is not None else os.environ.get("AUTH_BACKUP_ENCRYPTION_KEY", "")).strip()
    if len(text) < 32:
        raise _error(
            "BACKUP_KEY_MISSING",
            "AUTH_BACKUP_ENCRYPTION_KEY must be at least 32 characters",
        )
    if re.fullmatch(r"[0-9a-fA-F]+", text) and len(text) % 2 == 0 and len(text) >= 64:
        return bytes.fromhex(text)
    return text.encode("utf-8")


def encrypt_bytes(plaintext: bytes, key: bytes) -> bytes:
    nonce = os.urandom(12)
    stream = hashlib.shake_256(key + nonce).digest(len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return b"TM1" + nonce + tag + ciphertext


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    if not blob.startswith(b"TM1") or len(blob) < 3 + 12 + 32:
        raise _error("BACKUP_INVALID", "ciphertext is not a TokenMarket backup")
    nonce = blob[3:15]
    tag = blob[15:47]
    ciphertext = blob[47:]
    expect = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(expect, tag):
        raise _error("BACKUP_INVALID", "backup authentication failed")
    stream = hashlib.shake_256(key + nonce).digest(len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream))


def secure_mkdir(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_dir():
            raise _error("UNTRUSTED_PATH", f"refusing to use {path}")
        os.chmod(path, 0o700)
        return
    os.mkdir(path, 0o700)
    os.chmod(path, 0o700)


def secure_write_bytes(path: Path, data: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise _error(
            "UNTRUSTED_PATH", f"refusing to write {path}: {type(exc).__name__}"
        ) from exc
    try:
        os.write(fd, data)
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        raise _error("UNTRUSTED_PATH", f"{path} mode {oct(mode)} is not 0600")


def confirm_restore_matches(
    expected: Mapping[str, Sequence[Mapping[str, Any]]],
    actual: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    for table in _tables():
        exp_rows = [dict(r) for r in (expected.get(table) or [])]
        act_rows = [dict(r) for r in (actual.get(table) or [])]
        if len(exp_rows) != len(act_rows):
            raise _error(
                "RESTORE_MISMATCH",
                f"destination reread of {table} does not match the restore payload",
            )
        exp_ids = {str(r.get("id")) for r in exp_rows}
        act_ids = {str(r.get("id")) for r in act_rows}
        if exp_ids != act_ids:
            raise _error(
                "RESTORE_MISMATCH",
                f"destination reread of {table} does not match the restore payload",
            )
