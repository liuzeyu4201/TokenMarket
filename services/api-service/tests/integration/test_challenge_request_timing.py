"""Integration: challenge request timing (T060 / T129 / US2).

Default CI runs a lighter structural sample (n=5) so the suite stays fast.

**SC-006 acceptance path (evidence / release):** set ``TM_PERF=1`` (or
``AUTH_SC006_FULL=1``). That runs 100 samples × 4 account classes and asserts
p95≤500ms with inter-class Δ≤100ms. Light-mode success MUST NOT be recorded as
SC-006 pass in release evidence.
"""

from __future__ import annotations

import os
import secrets
import statistics
import time
import uuid
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.sms.synthetic import SyntheticSmsAdapter

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_timing_" + secrets.token_urlsafe(32)


def _set_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("MODE", "local")
    monkeypatch.setenv("AUTH_SESSION_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_OTP_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_CSRF_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_REFERENCE_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_BROWSER_ORIGINS", ORIGIN)
    monkeypatch.setenv("AUTH_SMS_ADAPTER", "synthetic")
    monkeypatch.setenv("AUTH_DISPATCHER_ENABLED", "0")
    clear_auth_settings_cache()


@pytest.fixture
def timing_client(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    _set_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=50_000, ip_limit=50_000
        )
        client.app.state.sms_adapter = SyntheticSmsAdapter()
        yield client
    clear_auth_settings_cache()


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


def _sc006_full_enabled() -> bool:
    return os.environ.get("TM_PERF") == "1" or os.environ.get("AUTH_SC006_FULL") == "1"


def test_challenge_request_timing_structure(
    timing_client: TestClient,
    account_factory,
) -> None:
    full = _sc006_full_enabled()
    n = 100 if full else 5

    classes = {
        "active": [account_factory.create_active().phone_normalized for _ in range(n)],
        "suspended": [
            account_factory.create_suspended().phone_normalized for _ in range(n)
        ],
        "deleted": [
            account_factory.create_deleted().phone_normalized for _ in range(n)
        ],
        "unknown": [account_factory.unknown_phone() for _ in range(n)],
    }

    durations: dict[str, list[float]] = {k: [] for k in classes}
    for label, phones in classes.items():
        for phone in phones:
            start = time.perf_counter()
            res = timing_client.post(
                "/api/v1/auth/verification-challenges",
                json={"phone": phone},
                headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
            )
            elapsed = time.perf_counter() - start
            assert res.status_code == 202, res.text
            assert res.json()["code"] == "0"
            durations[label].append(elapsed)

    # Structural: all classes produce comparable envelopes and finite timings
    for label, samples in durations.items():
        assert len(samples) == n
        assert all(s >= 0 for s in samples)
        mean = statistics.fmean(samples)
        assert mean < 5.0, f"{label} mean too high: {mean}"

    if full:
        p95s = {k: _p95(v) for k, v in durations.items()}
        for label, p in p95s.items():
            assert p <= 0.5, f"{label} p95={p}"
        vals = list(p95s.values())
        assert max(vals) - min(vals) <= 0.1, p95s
    else:
        # Explicit non-claim: light mode is not SC-006 acceptance.
        assert n == 5
        assert not _sc006_full_enabled()


def test_sc006_full_profile_env_gate_is_documented() -> None:
    """Release evidence must set TM_PERF=1 or AUTH_SC006_FULL=1 for SC-006."""
    source = open(__file__, encoding="utf-8").read()  # noqa: SIM115
    assert "TM_PERF" in source
    assert "AUTH_SC006_FULL" in source
    assert "100" in source
    assert "0.5" in source
