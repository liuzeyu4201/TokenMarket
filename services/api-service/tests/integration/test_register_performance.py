"""Env-gated p95 registration latency microbench (T077 / SC-004).

Set TM_REGISTER_PERF=1 to enable. Default CI skips this module.
"""

from __future__ import annotations

import os
import statistics
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.rate_limit import MemoryRateLimiter
from tests.integration.conftest_register import unique_phone

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("TM_REGISTER_PERF") != "1",
        reason="Set TM_REGISTER_PERF=1 to run p95 microbench",
    ),
]


def test_register_p95_under_500ms(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.main import app

    monkeypatch.setenv("DATABASE_URL", migrated_postgres)
    monkeypatch.delenv("REDIS_URL", raising=False)
    samples: list[float] = []
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter(
            ip_limit=10_000, phone_limit=10_000
        )
        for _ in range(20):
            start = time.perf_counter()
            r = client.post(
                "/api/v1/auth/register",
                json={
                    "phone": unique_phone(),
                    "nickname": "perf",
                    "role": "buyer",
                },
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            assert r.status_code == 200, r.text
            samples.append(elapsed_ms)
    samples_sorted = sorted(samples)
    p95 = samples_sorted[int(len(samples_sorted) * 0.95) - 1]
    assert p95 < 500, f"p95={p95:.1f}ms samples={samples}"
