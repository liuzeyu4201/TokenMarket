"""Usage log retention cleanup (SF17 FR-012).

Stable one-shot entrypoint (test/prod scheduler and local manual):

    python -m app.maintenance.usage_cleanup --retain-days 30

Deletes ``usage_logs`` (and matching ``usage_conflicts``) older than the
retain window. Does not start on API boot.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.domain.usage.service import UsageRecorder, UsageStore
from app.maintenance.auth_cleanup import _normalize_database_url
from app.repositories.sessioned import SessionedUsageStore

logger = logging.getLogger("api-service.usage_cleanup")

DEFAULT_RETAIN_DAYS = 30


@dataclass
class CleanupResult:
    outcome: str
    deleted: int = 0
    retain_days: int = DEFAULT_RETAIN_DAYS
    message: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "deleted": self.deleted,
            "retain_days": self.retain_days,
            "message": self.message,
        }


def run_cleanup(
    *,
    store: UsageStore | None = None,
    database_url: str | None = None,
    retain_days: int = DEFAULT_RETAIN_DAYS,
    now: datetime | None = None,
) -> CleanupResult:
    """Purge usage rows older than ``retain_days`` via the shipped recorder."""
    if retain_days < 1:
        raise ValueError("retain_days must be >= 1")
    own_engine = None
    if store is None:
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        sync_url = _normalize_database_url(database_url)
        own_engine = create_engine(sync_url, pool_pre_ping=True)
        store = SessionedUsageStore(sessionmaker(own_engine))
    try:
        when = now or datetime.now(timezone.utc)
        deleted = UsageRecorder(store=store).purge_expired(
            now=when, retain_days=retain_days
        )
        if own_engine is not None:
            cutoff = when - timedelta(days=retain_days)
            with own_engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM usage_conflicts WHERE created_at < :cutoff"),
                    {"cutoff": cutoff},
                )
        return CleanupResult(
            outcome="success", deleted=deleted, retain_days=retain_days
        )
    finally:
        if own_engine is not None:
            own_engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.maintenance.usage_cleanup",
        description="Delete usage_logs older than the retain window (SF17).",
    )
    parser.add_argument(
        "--retain-days",
        type=int,
        default=DEFAULT_RETAIN_DAYS,
        help=f"Retention days (default {DEFAULT_RETAIN_DAYS})",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL URL; defaults to DATABASE_URL",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.retain_days < 1:
        print(
            json.dumps({"outcome": "error", "message": "retain-days must be >= 1"}),
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
        result = run_cleanup(database_url=database_url, retain_days=args.retain_days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("usage cleanup failed")
        print(
            json.dumps({"outcome": "error", "message": type(exc).__name__}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result.to_public_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
