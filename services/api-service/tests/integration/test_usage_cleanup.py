"""SF17 30-day usage retention job drives the shipped CLI entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import PostgresHandle
from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def test_usage_cleanup_cli_deletes_old_rows(
    postgres_container: PostgresHandle,
) -> None:
    url = postgres_container.database_url()
    up = run_alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    engine = create_engine(url)
    old_id = uuid.uuid4()
    fresh_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO usage_logs (
                        usage_id, request_id, platform, model, usage_source,
                        partial, latency_ms, status_code, end_reason, created_at,
                        prompt_tokens, completion_tokens, total_tokens
                    ) VALUES (
                        :uid, :rid, 'volcano', 'm', 'official',
                        false, 1, 200, 'success', :created,
                        1, 1, 2
                    )
                    """
                ),
                {
                    "uid": old_id,
                    "rid": "old-rid",
                    "created": now - timedelta(days=31),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO usage_logs (
                        usage_id, request_id, platform, model, usage_source,
                        partial, latency_ms, status_code, end_reason, created_at,
                        prompt_tokens, completion_tokens, total_tokens
                    ) VALUES (
                        :uid, :rid, 'volcano', 'm', 'official',
                        false, 1, 200, 'success', :created,
                        1, 1, 2
                    )
                    """
                ),
                {"uid": fresh_id, "rid": "fresh-rid", "created": now},
            )
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.maintenance.usage_cleanup",
                "--retain-days",
                "30",
                "--database-url",
                url,
            ],
            cwd=str(SERVICE_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload["outcome"] == "success"
        assert payload["deleted"] >= 1
        with engine.connect() as conn:
            old_n = conn.execute(
                text("SELECT COUNT(*) FROM usage_logs WHERE request_id = 'old-rid'")
            ).scalar_one()
            fresh_n = conn.execute(
                text("SELECT COUNT(*) FROM usage_logs WHERE request_id = 'fresh-rid'")
            ).scalar_one()
        assert int(old_n) == 0
        assert int(fresh_n) == 1
    finally:
        engine.dispose()
