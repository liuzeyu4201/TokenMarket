from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.ledger import LedgerService
from app.domain.recon import ReconService
from app.main import app


def test_recon_event_and_unresolved_http() -> None:
    client = TestClient(app)
    client.__enter__()
    led = LedgerService()
    client.app.state.internal_token = "itok"
    client.app.state.ledger_service = led
    client.app.state.recon_service = ReconService(led)
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
        res = client.post(
            "/internal/v1/ledger/reserve",
            json={
                "request_id": "r-http",
                "idempotency_key": "r-http",
                "account_id": "a1",
                "project_id": "p1",
                "key_id": "k1",
                "amount_minor": 10,
                "rate_version": "rv-1",
            },
            headers={"X-Internal-Token": "itok"},
        )
        assert res.status_code == 200, res.text
        ev = client.post(
            "/internal/v1/recon/events",
            json={
                "event_id": "e1",
                "request_id": "r-http",
                "kind": "parse_failed",
            },
            headers={"X-Internal-Token": "itok"},
        )
        assert ev.status_code == 200, ev.text
        assert ev.json()["data"]["reason_code"] == "PARSE_FAILED"
        listed = client.get(
            "/internal/v1/recon/unresolved",
            headers={"X-Internal-Token": "itok"},
        )
        assert listed.status_code == 200
        assert listed.json()["data"]["items"][0]["reason_code"] == "PARSE_FAILED"
        daily = client.get(
            "/internal/v1/recon/daily",
            headers={"X-Internal-Token": "itok"},
        )
        assert daily.status_code == 200
        assert daily.json()["data"]["open_unresolved"] == 1
    finally:
        client.__exit__(None, None, None)
