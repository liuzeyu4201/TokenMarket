"""Authentication retention cleanup (SF04 / feature 004).

Stable one-shot entrypoint (test/prod scheduler and local manual):

    python -m app.maintenance.auth_cleanup --batch-size 500 --max-runtime-seconds 900

Deletes due authentication rows in small transactions under a single-owner
database advisory lock. Uses database ``NOW()`` for due decisions. Concurrent
invocations that miss the lock exit successfully as ``already_running``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url

from app.observability import emit_auth_event, record_auth_cleanup_rows

logger = logging.getLogger("api-service.auth_cleanup")

# Stable 64-bit key for pg_try_advisory_lock (session level).
# Derived from feature id so it does not collide with unrelated lockers.
AUTH_CLEANUP_ADVISORY_LOCK_KEY = 0x0040_0417_4355_5000  # 004 / cleanup

DEFAULT_BATCH_SIZE = 500
DEFAULT_MAX_RUNTIME_SECONDS = 900

# Delete order respects FK: events → sessions → challenges → idempotency.
CLEANUP_TABLES: tuple[str, ...] = (
    "authentication_security_events",
    "auth_sessions",
    "verification_challenges",
    "verification_request_idempotency_records",
)

# Metric / summary table labels (low cardinality).
_TABLE_LABELS: Mapping[str, str] = {
    "authentication_security_events": "security_events",
    "auth_sessions": "sessions",
    "verification_challenges": "challenges",
    "verification_request_idempotency_records": "idempotency",
}


@dataclass
class CleanupResult:
    """Desensitized summary of one cleanup invocation."""

    run_id: str
    outcome: str
    duration_seconds: float = 0.0
    rows_by_entity: dict[str, int] = field(default_factory=dict)
    batches: int = 0
    oldest_due_age_seconds: float | None = None
    message: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "outcome": self.outcome,
            "duration_seconds": round(self.duration_seconds, 3),
            "rows_by_entity": dict(self.rows_by_entity),
            "batches": self.batches,
            "oldest_due_age_seconds": self.oldest_due_age_seconds,
            "message": self.message,
        }


def _normalize_database_url(database_url: str) -> str:
    """Map async driver URLs onto a sync driver for the maintenance process."""
    url = make_url(database_url)
    if url.drivername in ("postgresql+asyncpg", "postgresql+psycopg2"):
        url = url.set(drivername="postgresql")
    elif url.drivername != "postgresql":
        raise ValueError("DATABASE_URL must use postgresql")
    return url.render_as_string(hide_password=False)


def _try_advisory_lock(conn: Connection) -> bool:
    acquired = conn.execute(
        text("SELECT pg_try_advisory_lock(:key)"),
        {"key": AUTH_CLEANUP_ADVISORY_LOCK_KEY},
    ).scalar_one()
    return bool(acquired)


def _advisory_unlock(conn: Connection) -> None:
    conn.execute(
        text("SELECT pg_advisory_unlock(:key)"),
        {"key": AUTH_CLEANUP_ADVISORY_LOCK_KEY},
    )


def _delete_batch(conn: Connection, table: str, batch_size: int) -> int:
    """Delete up to ``batch_size`` due rows from one table in the current txn.

    Selects with ``FOR UPDATE SKIP LOCKED`` so concurrent cleaners (if any
    bypassed the advisory lock) do not block each other, then deletes by id.
    """
    if table not in CLEANUP_TABLES:
        raise ValueError(f"unsupported cleanup table: {table}")
    if batch_size < 1:
        return 0

    # Identifier interpolation is safe: table is restricted to CLEANUP_TABLES.
    select_sql = text(
        f"""
        SELECT id
        FROM {table}
        WHERE delete_after <= NOW()
        ORDER BY delete_after ASC
        FOR UPDATE SKIP LOCKED
        LIMIT :limit
        """
    )
    ids = [row[0] for row in conn.execute(select_sql, {"limit": batch_size}).fetchall()]
    if not ids:
        return 0

    # Pass UUID strings as a text[] for psycopg2 compatibility.
    id_list = [str(i) for i in ids]
    result = conn.execute(
        text(
            f"""
            DELETE FROM {table}
            WHERE id IN (
                SELECT CAST(x AS uuid)
                FROM unnest(CAST(:ids AS text[])) AS x
            )
            """
        ),
        {"ids": id_list},
    )
    return int(result.rowcount or 0)


def _oldest_due_age_seconds(conn: Connection) -> float | None:
    """Return age in seconds of the oldest still-due row across cleanup tables."""
    ages: list[float] = []
    for table in CLEANUP_TABLES:
        row = conn.execute(
            text(
                f"""
                SELECT EXTRACT(EPOCH FROM (NOW() - MIN(delete_after)))
                FROM {table}
                WHERE delete_after <= NOW()
                """
            )
        ).scalar()
        if row is not None:
            ages.append(float(row))
    if not ages:
        return None
    return max(0.0, max(ages))


def run_cleanup(
    *,
    database_url: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_runtime_seconds: float = DEFAULT_MAX_RUNTIME_SECONDS,
    monotonic: Callable[[], float] | None = None,
    engine: Engine | None = None,
) -> CleanupResult:
    """Execute one bounded cleanup run.

    Parameters
    ----------
    database_url:
        Operator-provided PostgreSQL URL (sync or async driver form).
    batch_size:
        Max rows deleted per table per transaction (default 500).
    max_runtime_seconds:
        Wall-clock budget for the whole invocation (default 900).
    monotonic:
        Clock for runtime budget (injectable for tests).
    engine:
        Optional pre-built engine (tests); otherwise created from URL.
    """
    clock = monotonic or time.monotonic
    run_id = str(uuid.uuid4())
    started = clock()
    rows_by_entity: dict[str, int] = {label: 0 for label in _TABLE_LABELS.values()}
    batches = 0

    own_engine = engine is None
    eng = engine or create_engine(
        _normalize_database_url(database_url), pool_pre_ping=True
    )

    try:
        # Hold a single connection for the session-level advisory lock.
        with eng.connect() as lock_conn:
            if not _try_advisory_lock(lock_conn):
                result = CleanupResult(
                    run_id=run_id,
                    outcome="already_running",
                    duration_seconds=clock() - started,
                    message="advisory lock held by another cleanup invocation",
                )
                emit_auth_event(
                    logger,
                    "auth.cleanup.completed",
                    run_id=run_id,
                    outcome=result.outcome,
                )
                return result

            # Keep lock_conn open (and unused for DML) while work runs on
            # separate connections/transactions so COMMIT does not release
            # the session lock held by lock_conn.
            try:
                while True:
                    elapsed = clock() - started
                    if elapsed >= max_runtime_seconds:
                        break

                    round_deleted = 0
                    with eng.begin() as work:
                        for table in CLEANUP_TABLES:
                            if clock() - started >= max_runtime_seconds:
                                break
                            deleted = _delete_batch(work, table, batch_size)
                            if deleted:
                                label = _TABLE_LABELS[table]
                                rows_by_entity[label] = (
                                    rows_by_entity.get(label, 0) + deleted
                                )
                                record_auth_cleanup_rows(label, deleted)
                                round_deleted += deleted
                                batches += 1

                    if round_deleted == 0:
                        break

                with eng.connect() as probe:
                    oldest = _oldest_due_age_seconds(probe)

                outcome = "success"
                if oldest is not None and oldest > 0:
                    # Budget exhausted with remaining due work is still a
                    # successful partial run; alerts watch backlog age.
                    if clock() - started >= max_runtime_seconds:
                        outcome = "budget_exhausted"

                result = CleanupResult(
                    run_id=run_id,
                    outcome=outcome,
                    duration_seconds=clock() - started,
                    rows_by_entity=rows_by_entity,
                    batches=batches,
                    oldest_due_age_seconds=oldest,
                )
                emit_auth_event(
                    logger,
                    "auth.cleanup.completed",
                    run_id=run_id,
                    outcome=result.outcome,
                    batches=batches,
                    rows=sum(rows_by_entity.values()),
                )
                return result
            finally:
                _advisory_unlock(lock_conn)
    finally:
        if own_engine:
            eng.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.maintenance.auth_cleanup",
        description="Bounded authentication retention cleanup (single-owner).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Max rows per table per transaction (default {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=DEFAULT_MAX_RUNTIME_SECONDS,
        help=f"Wall-clock budget seconds (default {DEFAULT_MAX_RUNTIME_SECONDS})",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL URL; defaults to DATABASE_URL environment variable",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    if args.batch_size < 1:
        print(
            json.dumps({"outcome": "error", "message": "batch-size must be >= 1"}),
            file=sys.stderr,
        )
        return 2
    if args.max_runtime_seconds <= 0:
        print(
            json.dumps(
                {"outcome": "error", "message": "max-runtime-seconds must be > 0"}
            ),
            file=sys.stderr,
        )
        return 2

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        print(
            json.dumps({"outcome": "error", "message": "DATABASE_URL is required"}),
            file=sys.stderr,
        )
        return 2

    try:
        result = run_cleanup(
            database_url=database_url,
            batch_size=args.batch_size,
            max_runtime_seconds=args.max_runtime_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — surface safe summary only
        logger.exception("auth cleanup failed")
        print(
            json.dumps(
                {
                    "outcome": "error",
                    "message": type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result.to_public_dict(), sort_keys=True))
    # already_running and success are both zero-exit for scheduler safety.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
