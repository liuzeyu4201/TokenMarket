from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.budget import BudgetService, MemoryLedgerView, QuotaView
from app.domain.projects.service import ProjectService
from app.domain.projects.store import MemoryProjectStore
from app.main import app


def test_guide_and_budget_http() -> None:
    user = uuid.uuid4()
    projects = MemoryProjectStore()
    proj = ProjectService(store=projects)
    rec = proj.create(
        owner_id=user,
        display_name="BudP",
        mode="shared",
        enabled_protocols=["openai"],
        role="buyer",
        workspace="buyer",
        request_id="c1",
    )
    ledger = MemoryLedgerView()
    ledger.put(
        str(rec.project_id),
        QuotaView(available=100, reserved=0, settled=0, unresolved=0),
    )
    bud = BudgetService(ledger=ledger, projects=proj)
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role="buyer", status="active", workspace="buyer"
    )
    client.app.state.project_service = proj
    client.app.state.budget_service = bud
    try:
        g = client.get(f"/api/v1/projects/{rec.project_id}/guide")
        assert g.status_code == 200, g.text
        assert "x-api-key" in g.text
        assert ":generateContent" in g.text
        assert "充值" not in g.text or "不可" in g.json()["data"]["disclaimer"]
        b = client.get(f"/api/v1/projects/{rec.project_id}/budget")
        assert b.status_code == 200
        assert b.json()["data"]["available"] == 100
        saved = client.put(
            f"/api/v1/projects/{rec.project_id}/budget",
            json={"hard_minor": 100, "soft_minor": 20},
        )
        assert saved.status_code == 200, saved.text
        ok = client.post(
            f"/api/v1/projects/{rec.project_id}/budget/admit",
            json={"amount_minor": 10},
        )
        assert ok.status_code == 200, ok.text
        denied = client.post(
            f"/api/v1/projects/{rec.project_id}/budget/admit",
            json={"amount_minor": 999},
        )
        assert denied.status_code == 409
        usage = client.get(f"/api/v1/projects/{rec.project_id}/usage")
        assert usage.status_code == 200
    finally:
        client.__exit__(None, None, None)
