"""HTTP registration happy path (requires DATABASE_URL + migrated schema).

Skipped when TM_REGISTER_INTEGRATION is not set so unit CI remains hermetic.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rate_limit import MemoryRateLimiter

pytestmark = pytest.mark.skipif(
    os.environ.get("TM_REGISTER_INTEGRATION") != "1",
    reason="Set TM_REGISTER_INTEGRATION=1 with migrated DATABASE_URL to run",
)


@pytest.fixture
def register_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    url = os.environ["DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        yield client


def test_register_success(register_client: TestClient) -> None:
    phone = f"138{uuid.uuid4().int % 10**8:08d}"[:11]
    # ensure second digit is 3-9
    phone = "138" + phone[3:]
    key = str(uuid.uuid4())
    res = register_client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "nickname": "集成用户", "role": "buyer"},
        headers={"Idempotency-Key": key},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["code"] == "0"
    assert body["data"]["role"] == "buyer"
    assert body["data"]["status"] == "active"
    assert "user_id" in body["data"]
    assert "138" not in res.text or body["data"].get("phone_masked", "").startswith("*")
