from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.ledger import LedgerService
from app.main import app


def _client() -> TestClient:
    client = TestClient(app)
    client.__enter__()
    client.app.state.internal_token = "itok"
    client.app.state.ledger_service = LedgerService()
    return client


def test_reserve_settle_balance_http() -> None:
    client = _client()
    try:
        seed = client.post(
            "/internal/v1/ledger/seed-test-quota",
            json={
                "account_id": "a1",
                "project_id": "p1",
                "key_id": "k1",
                "account_grant": 100,
                "project_grant": 100,
                "key_grant": 100,
            },
            headers={"X-Internal-Token": "itok"},
        )
        assert seed.status_code == 200, seed.text
        denied = client.post(
            "/internal/v1/ledger/reserve",
            json={
                "request_id": "r1",
                "idempotency_key": "r1",
                "account_id": "a1",
                "project_id": "p1",
                "key_id": "k1",
                "amount_minor": 10,
                "rate_version": "rv-1",
            },
        )
        assert denied.status_code == 401
        res = client.post(
            "/internal/v1/ledger/reserve",
            json={
                "request_id": "r1",
                "idempotency_key": "r1",
                "account_id": "a1",
                "project_id": "p1",
                "key_id": "k1",
                "amount_minor": 10,
                "rate_version": "rv-1",
            },
            headers={"X-Internal-Token": "itok"},
        )
        assert res.status_code == 200, res.text
        stl = client.post(
            "/internal/v1/ledger/settle",
            json={
                "request_id": "r1",
                "buyer_debit": 8,
                "seller_earning": 6,
                "spread": 2,
                "seller_id": "s1",
                "rate_version": "rv-1",
                "evidence_digest": "d1",
            },
            headers={"X-Internal-Token": "itok"},
        )
        assert stl.status_code == 200, stl.text
        bal = client.get(
            "/internal/v1/ledger/balance/buyer_quota/a1",
            headers={"X-Internal-Token": "itok"},
        )
        assert bal.status_code == 200
        assert bal.json()["data"]["available"] == 92
        assert "/recharge" not in str(app.routes)
        assert "/withdraw" not in str(app.routes)
    finally:
        client.__exit__(None, None, None)
