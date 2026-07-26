"""Isolated authentication table backup, restore, and invariant checks (004 T100).

Operators (and evidence runs) use this module against an *isolated* PostgreSQL
15 database — never against a shared developer or production DSN without an
explicit recovery plan.

Capabilities
------------
1. Logical export of auth tables (JSON) from a source ``DATABASE_URL``.
2. Optional ``pg_dump`` / ``pg_restore`` path when those binaries are available;
   logs always redact userinfo in connection strings.
3. Restore into a *fresh* destination database URL.
4. Static invariant verification on restored (or synthetic) rows:
   - at most one active session per user (``revoked_at IS NULL``)
   - consumed challenges remain consumed (state + timestamps + cleared digest)
   - ``send_started_at`` work is never treated as resend-eligible
     (must not sit in ``pending_delivery``)

Redacted manifests contain only table names, row counts, and opaque UUID
references — never passwords, phones, OTP material, cookies, CSRF, or HMAC keys.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

AUTH_TABLES: tuple[str, ...] = (
    "verification_request_idempotency_records",
    "verification_challenges",
    "auth_sessions",
    "authentication_security_events",
)

# States that may legitimately carry a non-null send_started_at (data-model.md).
_SEND_STARTED_ALLOWED_STATES = frozenset(
    {
        "dispatching",
        "delivered",
        "delivery_failed",
        "consumed",
        "locked",
        "superseded",
        "expired",
    }
)

# Challenge states that must never be re-sent once send has started.
_RESEND_ELIGIBLE_STATES = frozenset({"pending_delivery"})

_URL_USERINFO_RE = re.compile(r"(://[^:/?#\s]+):([^@/\s]+)@")
_SECRET_FRAGMENT_RE = re.compile(r"tm_local_[A-Za-z0-9_-]{8,}")


class AuthBackupError(Exception):
    """Fail-closed backup/restore/verify error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class InvariantViolation:
    code: str
    message: str
    subject_id: str | None = None


@dataclass
class InvariantReport:
    ok: bool
    violations: list[InvariantViolation] = field(default_factory=list)

    def raise_if_failed(self) -> None:
        if self.ok:
            return
        summary = "; ".join(f"[{v.code}] {v.message}" for v in self.violations[:5])
        raise AuthBackupError("INVARIANT_VIOLATION", summary or "auth invariants failed")


@dataclass
class RedactedManifest:
    """Safe pre/post backup summary — safe to write into evidence."""

    schema_version: str
    kind: str
    created_at: str
    tables: dict[str, dict[str, Any]]
    tool: str
    notes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackupArtifact:
    """Paths produced by a backup run."""

    export_path: Path
    manifest_path: Path
    method: str  # "logical-json" | "pg_dump"
    redacted_source: str


def redact_database_url(url: str) -> str:
    """Return a connection string with password (and tm_local_ secrets) redacted."""
    if not url:
        return ""
    redacted = _URL_USERINFO_RE.sub(r"\1:[REDACTED]@", url)
    redacted = _SECRET_FRAGMENT_RE.sub("[REDACTED]", redacted)
    return redacted


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_mapping_rows(rows: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if not rows:
        return []
    return [dict(r) for r in rows]


def verify_auth_invariants(
    *,
    challenges: Sequence[Mapping[str, Any]] | None = None,
    sessions: Sequence[Mapping[str, Any]] | None = None,
    idempotency: Sequence[Mapping[str, Any]] | None = None,
) -> InvariantReport:
    """Statically verify auth recovery invariants on row mappings.

    Does not contact a database. Suitable for unit tests with synthetic rows and
    for post-restore validation of loaded logical exports.
    """
    violations: list[InvariantViolation] = []
    challenge_rows = _as_mapping_rows(challenges)
    session_rows = _as_mapping_rows(sessions)
    _ = _as_mapping_rows(idempotency)  # reserved for future unique-key checks

    # --- at most one active session per user ---
    active_by_user: dict[str, list[str]] = {}
    for row in session_rows:
        revoked = row.get("revoked_at")
        if revoked is not None and str(revoked).strip() != "":
            continue
        user_id = str(row.get("user_id") or "")
        sid = str(row.get("id") or "")
        if not user_id:
            violations.append(
                InvariantViolation(
                    "SESSION_MISSING_USER",
                    "active session row missing user_id",
                    subject_id=sid or None,
                )
            )
            continue
        active_by_user.setdefault(user_id, []).append(sid)

    for user_id, sids in sorted(active_by_user.items()):
        if len(sids) > 1:
            violations.append(
                InvariantViolation(
                    "MULTIPLE_ACTIVE_SESSIONS",
                    f"user {user_id} has {len(sids)} active sessions (ids={sids})",
                    subject_id=user_id,
                )
            )

    # --- consumed challenges stay consumed; send_started not resendable ---
    for row in challenge_rows:
        cid = str(row.get("id") or "") or None
        state = str(row.get("state") or "").strip()
        send_started = row.get("send_started_at")
        consumed_at = row.get("consumed_at")
        code_digest = row.get("code_digest")

        if state == "consumed":
            if consumed_at is None or str(consumed_at).strip() == "":
                violations.append(
                    InvariantViolation(
                        "CONSUMED_MISSING_TIMESTAMP",
                        "consumed challenge missing consumed_at",
                        subject_id=cid,
                    )
                )
            # Digest must be cleared on terminal consume (usable? no).
            if code_digest not in (None, b"", "", []):
                violations.append(
                    InvariantViolation(
                        "CONSUMED_DIGEST_PRESENT",
                        "consumed challenge still has code_digest material",
                        subject_id=cid,
                    )
                )

        has_send_started = send_started is not None and str(send_started).strip() != ""
        if has_send_started:
            if state in _RESEND_ELIGIBLE_STATES:
                violations.append(
                    InvariantViolation(
                        "SEND_STARTED_RESEND_ELIGIBLE",
                        "send_started_at set but state is still resend-eligible "
                        f"({state!r}); recovery must query or invalidate, never resend",
                        subject_id=cid,
                    )
                )
            if state not in _SEND_STARTED_ALLOWED_STATES and state not in _RESEND_ELIGIBLE_STATES:
                # Unknown/illegal combination still flagged for recovery evidence.
                violations.append(
                    InvariantViolation(
                        "SEND_STARTED_ILLEGAL_STATE",
                        f"send_started_at set with unexpected state {state!r}",
                        subject_id=cid,
                    )
                )

    return InvariantReport(ok=not violations, violations=violations)


def build_redacted_manifest(
    *,
    table_stats: Mapping[str, Mapping[str, Any]],
    tool: str = "workflow.auth_backup_restore",
    notes: Mapping[str, Any] | None = None,
) -> RedactedManifest:
    """Build a redacted manifest from per-table stats (counts + opaque ids)."""
    safe_tables: dict[str, dict[str, Any]] = {}
    for name, stats in table_stats.items():
        row_count = int(stats.get("row_count", 0))
        opaque_ids = list(stats.get("opaque_ids") or [])
        # Cap ids stored in evidence to avoid huge manifests.
        safe_tables[name] = {
            "row_count": row_count,
            "opaque_ids": [str(i) for i in opaque_ids[:200]],
            "opaque_ids_truncated": len(opaque_ids) > 200,
        }
    return RedactedManifest(
        schema_version="1.0.0",
        kind="tokenmarket.auth_backup_manifest",
        created_at=_utc_now_iso(),
        tables=safe_tables,
        tool=tool,
        notes=dict(notes or {}),
    )


def _logical_export_payload(
    *,
    challenges: Sequence[Mapping[str, Any]],
    sessions: Sequence[Mapping[str, Any]],
    idempotency: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "kind": "tokenmarket.auth_logical_export",
        "exported_at": _utc_now_iso(),
        "tables": {
            "verification_challenges": _as_mapping_rows(challenges),
            "auth_sessions": _as_mapping_rows(sessions),
            "verification_request_idempotency_records": _as_mapping_rows(idempotency),
            "authentication_security_events": _as_mapping_rows(events),
        },
    }


def write_logical_export(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(body, encoding="utf-8")


def read_logical_export(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AuthBackupError("BACKUP_MISSING", f"logical export not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthBackupError("BACKUP_INVALID", f"export is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AuthBackupError("BACKUP_INVALID", "export root must be an object")
    return data


def verify_export_payload(payload: Mapping[str, Any]) -> InvariantReport:
    """Run invariant checks against a logical export payload."""
    tables = payload.get("tables") or {}
    if not isinstance(tables, dict):
        raise AuthBackupError("BACKUP_INVALID", "tables must be an object")
    return verify_auth_invariants(
        challenges=tables.get("verification_challenges") or [],
        sessions=tables.get("auth_sessions") or [],
        idempotency=tables.get("verification_request_idempotency_records") or [],
    )


def stats_from_export(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    tables = payload.get("tables") or {}
    out: dict[str, dict[str, Any]] = {}
    for name in AUTH_TABLES:
        rows = tables.get(name) or []
        if not isinstance(rows, list):
            rows = []
        ids = [str(r.get("id")) for r in rows if isinstance(r, dict) and r.get("id")]
        out[name] = {"row_count": len(rows), "opaque_ids": ids}
    return out


def backup_from_rows(
    *,
    output_dir: Path,
    challenges: Sequence[Mapping[str, Any]],
    sessions: Sequence[Mapping[str, Any]],
    idempotency: Sequence[Mapping[str, Any]] | None = None,
    events: Sequence[Mapping[str, Any]] | None = None,
    source_url_redacted: str = "synthetic",
) -> BackupArtifact:
    """Write a logical export + redacted manifest from in-memory rows (tests/offline)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    export_path = output_dir / "auth_tables.json"
    manifest_path = output_dir / "auth_backup_manifest.json"
    payload = _logical_export_payload(
        challenges=challenges,
        sessions=sessions,
        idempotency=idempotency or [],
        events=events or [],
    )
    # Fail closed if source data already violates invariants.
    report = verify_export_payload(payload)
    report.raise_if_failed()

    write_logical_export(export_path, payload)
    manifest = build_redacted_manifest(
        table_stats=stats_from_export(payload),
        notes={
            "source": source_url_redacted,
            "export_sha256": _sha256_file(export_path),
            "method": "logical-json",
        },
    )
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return BackupArtifact(
        export_path=export_path,
        manifest_path=manifest_path,
        method="logical-json",
        redacted_source=source_url_redacted,
    )


def restore_logical_export_to_memory(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load a logical export for in-process restore/verify (no database)."""
    payload = read_logical_export(path)
    tables = payload.get("tables") or {}
    if not isinstance(tables, dict):
        raise AuthBackupError("BACKUP_INVALID", "tables must be an object")
    restored: dict[str, list[dict[str, Any]]] = {}
    for name in AUTH_TABLES:
        rows = tables.get(name) or []
        if not isinstance(rows, list):
            raise AuthBackupError("BACKUP_INVALID", f"table {name} must be an array")
        restored[name] = [dict(r) for r in rows if isinstance(r, dict)]
    return restored


def backup_restore_verify_memory(
    *,
    challenges: Sequence[Mapping[str, Any]],
    sessions: Sequence[Mapping[str, Any]],
    work_dir: Path,
    idempotency: Sequence[Mapping[str, Any]] | None = None,
    events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """End-to-end offline path: export → restore-to-memory → re-verify invariants."""
    artifact = backup_from_rows(
        output_dir=work_dir,
        challenges=challenges,
        sessions=sessions,
        idempotency=idempotency,
        events=events,
    )
    restored = restore_logical_export_to_memory(artifact.export_path)
    report = verify_auth_invariants(
        challenges=restored["verification_challenges"],
        sessions=restored["auth_sessions"],
        idempotency=restored["verification_request_idempotency_records"],
    )
    report.raise_if_failed()
    pre = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    post_stats = {
        name: {
            "row_count": len(restored[name]),
            "opaque_ids": [str(r.get("id")) for r in restored[name] if r.get("id")],
        }
        for name in AUTH_TABLES
    }
    for name in AUTH_TABLES:
        if pre["tables"][name]["row_count"] != post_stats[name]["row_count"]:
            raise AuthBackupError(
                "ROW_COUNT_MISMATCH",
                f"table {name}: backup count {pre['tables'][name]['row_count']} "
                f"!= restored {post_stats[name]['row_count']}",
            )
    return {
        "ok": True,
        "method": artifact.method,
        "export_path": str(artifact.export_path),
        "manifest_path": str(artifact.manifest_path),
        "export_sha256": pre["notes"].get("export_sha256"),
        "tables": post_stats,
    }


# ---------------------------------------------------------------------------
# Optional live PostgreSQL helpers (pg_dump or asyncpg logical export)
# ---------------------------------------------------------------------------


def _which(binary: str) -> str | None:
    return shutil.which(binary)


def _run_redacted(
    cmd: list[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess; never raise with secret-bearing argv in the message."""
    result = subprocess.run(
        cmd,
        env=dict(env) if env is not None else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return result


def document_pg_dump_command(database_url: str, dump_path: Path) -> str:
    """Return a redacted operator-facing pg_dump recipe for auth tables.

    Prefer invoking via PGPASSWORD / connection URI outside of shell history
    when possible. The returned string always redacts userinfo.
    """
    redacted = redact_database_url(database_url)
    table_args = " ".join(f"--table=public.{t}" for t in AUTH_TABLES)
    return (
        f"pg_dump --format=custom --no-owner --no-acl {table_args} "
        f"--file={dump_path} {redacted}"
    )


async def _fetch_auth_tables_async(database_url: str) -> dict[str, list[dict[str, Any]]]:
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        out: dict[str, list[dict[str, Any]]] = {}
        for table in AUTH_TABLES:
            try:
                records = await conn.fetch(f'SELECT * FROM "{table}"')  # noqa: S608
            except asyncpg.UndefinedTableError as exc:
                raise AuthBackupError(
                    "TABLE_MISSING",
                    f"auth table missing in source database: {table}",
                ) from exc
            rows: list[dict[str, Any]] = []
            for rec in records:
                row = dict(rec)
                # Normalize non-JSON-friendly values.
                for key, value in list(row.items()):
                    if isinstance(value, memoryview):
                        row[key] = bytes(value)
                    elif isinstance(value, bytes):
                        row[key] = value.hex() if value else None
                    elif hasattr(value, "isoformat"):
                        row[key] = value.isoformat()
                    elif value is not None and not isinstance(
                        value, (str, int, float, bool, list, dict)
                    ):
                        row[key] = str(value)
                rows.append(row)
            out[table] = rows
        return out
    finally:
        await conn.close()


def backup_database(
    database_url: str,
    output_dir: Path,
    *,
    prefer_pg_dump: bool = True,
) -> BackupArtifact:
    """Backup auth tables from ``database_url`` into ``output_dir``.

    Uses ``pg_dump`` (custom format) when available and ``prefer_pg_dump`` is
    true; otherwise performs a logical JSON export via asyncpg. Logs and
    manifests never include raw passwords.
    """
    if not database_url or "://" not in database_url:
        raise AuthBackupError("INVALID_URL", "DATABASE_URL is missing or malformed")

    redacted = redact_database_url(database_url)
    output_dir.mkdir(parents=True, exist_ok=True)

    if prefer_pg_dump and _which("pg_dump"):
        dump_path = output_dir / "auth_tables.dump"
        cmd = [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            f"--file={dump_path}",
        ]
        for table in AUTH_TABLES:
            cmd.append(f"--table=public.{table}")
        cmd.append(database_url)
        result = _run_redacted(cmd, timeout=300)
        if result.returncode != 0:
            safe_err = redact_database_url((result.stderr or result.stdout or "")[:400])
            raise AuthBackupError("PG_DUMP_FAILED", f"pg_dump failed: {safe_err}")

        # Also write a logical JSON snapshot for invariant verification without
        # requiring restore mid-flight (best-effort; falls back if asyncpg fails).
        try:
            logical = _sync_fetch_tables(database_url)
            payload = {
                "schema_version": "1.0.0",
                "kind": "tokenmarket.auth_logical_export",
                "exported_at": _utc_now_iso(),
                "tables": logical,
            }
            export_path = output_dir / "auth_tables.json"
            write_logical_export(export_path, payload)
            report = verify_export_payload(payload)
            report.raise_if_failed()
            stats = stats_from_export(payload)
            export_sha = _sha256_file(export_path)
        except AuthBackupError:
            raise
        except Exception:
            export_path = dump_path
            stats = {t: {"row_count": -1, "opaque_ids": []} for t in AUTH_TABLES}
            export_sha = _sha256_file(dump_path)

        manifest_path = output_dir / "auth_backup_manifest.json"
        manifest = build_redacted_manifest(
            table_stats=stats,
            notes={
                "source": redacted,
                "method": "pg_dump",
                "export_sha256": export_sha,
                "pg_dump_recipe": document_pg_dump_command(database_url, dump_path),
            },
        )
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return BackupArtifact(
            export_path=dump_path if dump_path.is_file() else export_path,
            manifest_path=manifest_path,
            method="pg_dump",
            redacted_source=redacted,
        )

    # Logical JSON via asyncpg
    logical = _sync_fetch_tables(database_url)
    payload = {
        "schema_version": "1.0.0",
        "kind": "tokenmarket.auth_logical_export",
        "exported_at": _utc_now_iso(),
        "tables": logical,
    }
    report = verify_export_payload(payload)
    report.raise_if_failed()
    export_path = output_dir / "auth_tables.json"
    write_logical_export(export_path, payload)
    manifest_path = output_dir / "auth_backup_manifest.json"
    manifest = build_redacted_manifest(
        table_stats=stats_from_export(payload),
        notes={
            "source": redacted,
            "method": "logical-json",
            "export_sha256": _sha256_file(export_path),
        },
    )
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return BackupArtifact(
        export_path=export_path,
        manifest_path=manifest_path,
        method="logical-json",
        redacted_source=redacted,
    )


def _sync_fetch_tables(database_url: str) -> dict[str, list[dict[str, Any]]]:
    import asyncio

    return asyncio.run(_fetch_auth_tables_async(database_url))


def restore_database(
    database_url: str,
    backup: Path,
    *,
    method: str | None = None,
) -> InvariantReport:
    """Restore auth backup into a *fresh* destination database and verify invariants.

    ``backup`` may be a ``pg_dump`` custom-format file or a logical JSON export.
    Destination must already have the auth schema (migrations applied).
    """
    if not database_url or "://" not in database_url:
        raise AuthBackupError("INVALID_URL", "destination DATABASE_URL is missing or malformed")
    if not backup.is_file():
        raise AuthBackupError("BACKUP_MISSING", f"backup not found: {backup}")

    resolved_method = method
    if resolved_method is None:
        if backup.suffix == ".dump":
            resolved_method = "pg_dump"
        elif backup.suffix == ".json":
            resolved_method = "logical-json"
        else:
            # Sniff JSON
            head = backup.read_bytes()[:32].lstrip()
            resolved_method = "logical-json" if head.startswith(b"{") else "pg_dump"

    if resolved_method == "pg_dump":
        if not _which("pg_restore"):
            raise AuthBackupError("TOOL_MISSING", "pg_restore is not installed")
        cmd = [
            "pg_restore",
            "--no-owner",
            "--no-acl",
            "--data-only",
            f"--dbname={database_url}",
            str(backup),
        ]
        result = _run_redacted(cmd, timeout=300)
        if result.returncode != 0:
            safe_err = redact_database_url((result.stderr or result.stdout or "")[:400])
            raise AuthBackupError("PG_RESTORE_FAILED", f"pg_restore failed: {safe_err}")
        # Re-read and verify
        logical = _sync_fetch_tables(database_url)
        return verify_auth_invariants(
            challenges=logical.get("verification_challenges"),
            sessions=logical.get("auth_sessions"),
            idempotency=logical.get("verification_request_idempotency_records"),
        )

    if resolved_method == "logical-json":
        restored = restore_logical_export_to_memory(backup)
        _insert_logical_rows(database_url, restored)
        return verify_auth_invariants(
            challenges=restored["verification_challenges"],
            sessions=restored["auth_sessions"],
            idempotency=restored["verification_request_idempotency_records"],
        )

    raise AuthBackupError("BACKUP_INVALID", f"unknown restore method {resolved_method!r}")


async def _insert_logical_rows_async(
    database_url: str,
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        # Dependency-friendly order: idempotency → challenges → sessions → events
        order = (
            "verification_request_idempotency_records",
            "verification_challenges",
            "auth_sessions",
            "authentication_security_events",
        )
        for table in order:
            rows = tables.get(table) or []
            if not rows:
                continue
            for row in rows:
                cols = list(row.keys())
                if not cols:
                    continue
                col_sql = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
                values = [_coerce_pg_value(row[c]) for c in cols]
                sql = f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders})'  # noqa: S608
                try:
                    await conn.execute(sql, *values)
                except Exception as exc:  # pragma: no cover - driver specific
                    raise AuthBackupError(
                        "RESTORE_INSERT_FAILED",
                        f"insert into {table} failed: {type(exc).__name__}",
                    ) from exc
    finally:
        await conn.close()


def _coerce_pg_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) == 32 and all(
        c in "0123456789abcdef" for c in value.lower()
    ):
        # Heuristic: hex-encoded short digest → keep as string; real BYTEA restore
        # for evidence paths should use pg_dump. Logical path accepts text/nulls.
        return value
    return value


def _insert_logical_rows(
    database_url: str,
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    import asyncio

    asyncio.run(_insert_logical_rows_async(database_url, tables))


def backup_restore_verify(
    source_url: str,
    dest_url: str,
    work_dir: Path,
    *,
    prefer_pg_dump: bool = True,
) -> dict[str, Any]:
    """Full live path: backup source → restore dest → verify invariants + counts."""
    if source_url.strip() == dest_url.strip():
        raise AuthBackupError(
            "SAME_DATABASE",
            "source and destination DATABASE_URL must differ for restore evidence",
        )
    artifact = backup_database(source_url, work_dir, prefer_pg_dump=prefer_pg_dump)
    # Prefer logical JSON for invariant + insert path when present.
    logical_path = work_dir / "auth_tables.json"
    backup_path = logical_path if logical_path.is_file() else artifact.export_path
    report = restore_database(dest_url, backup_path)
    report.raise_if_failed()

    pre = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    post = _sync_fetch_tables(dest_url)
    for name in AUTH_TABLES:
        pre_count = pre["tables"][name]["row_count"]
        post_count = len(post.get(name) or [])
        if pre_count >= 0 and pre_count != post_count:
            raise AuthBackupError(
                "ROW_COUNT_MISMATCH",
                f"table {name}: backup count {pre_count} != restored {post_count}",
            )
    return {
        "ok": True,
        "method": artifact.method,
        "source": redact_database_url(source_url),
        "destination": redact_database_url(dest_url),
        "export_path": str(artifact.export_path),
        "manifest_path": str(artifact.manifest_path),
        "invariants_ok": True,
    }


def docker_available() -> bool:
    """Return True when the Docker CLI can talk to a daemon (optional live tests)."""
    if not _which("docker"):
        return False
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    return result.returncode == 0


def isolated_database_url_from_env() -> str | None:
    """Return an optional isolated DATABASE_URL for live backup tests."""
    for key in ("AUTH_BACKUP_TEST_DATABASE_URL", "AUTH_BACKUP_SOURCE_DATABASE_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None
