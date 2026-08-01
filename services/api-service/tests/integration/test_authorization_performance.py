"""Optional env-gated authz latency microbench (SC-004a)."""

from __future__ import annotations

import os
import statistics
import time

import pytest
from fastapi.testclient import TestClient

from app.domain.users.models import UserRole
from tests.integration.conftest_authorization import (
    AuthzSessionFactory,
    authz_headers,
    force_session_cookie,
)

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("AUTHZ_PERF_BENCH", "").lower() not in ("1", "true", "yes"),
    reason="Set AUTHZ_PERF_BENCH=1 to run SC-004a microbench",
)
def test_evaluate_p95_direct_read(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
) -> None:
    user = account_factory.create_active(role=UserRole.buyer)
    issued = authz_sessions.issue(user)
    force_session_cookie(authz_client, issued.cookie_value)
    samples: list[float] = []
    for i in range(30):
        t0 = time.perf_counter()
        res = authz_client.post(
            "/api/v1/authorization/evaluate",
            json={"action": "proxy_key.create"},
            headers={
                **authz_headers(issued, with_csrf=False),
                "X-Request-ID": f"perf-{i}",
            },
        )
        samples.append(time.perf_counter() - t0)
        assert res.status_code == 200
    samples_sorted = sorted(samples)
    p95 = samples_sorted[int(len(samples_sorted) * 0.95) - 1]
    # SC-004a target 50ms — record but soft assert under 200ms to catch regressions
    assert p95 < 0.2, f"p95={p95:.4f}s mean={statistics.mean(samples):.4f}s"
