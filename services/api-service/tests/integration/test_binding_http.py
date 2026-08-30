"""Binding HTTP against migrated PostgreSQL."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache
from app.domain.bindings.ports import AlwaysPriceLookup
from app.domain.bindings.service import BindingError, BindingService
from app.domain.users.models import UserRole
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.repositories.bindings import SessionedBindingStore
from app.repositories.projects import SessionedProjectStore
from app.sms.synthetic import SyntheticSmsAdapter
from tests.integration.test_session_lifecycle import _login_client

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_bind_" + "y" * 40


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
def bind_client(
    auth_migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    _set_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        client.app.state.sms_adapter = SyntheticSmsAdapter()
        yield client
    clear_auth_settings_cache()


def _headers(csrf: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf}


def test_publish_three_protocols_and_sql_single_active(
    bind_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(role=UserRole.buyer)
    csrf = _login_client(bind_client, user.phone_normalized, auth_migrated_postgres)
    created = bind_client.post(
        "/api/v1/projects",
        json={
            "display_name": "BindLive",
            "mode": "shared",
            "enabled_protocols": ["openai"],
        },
        headers=_headers(csrf),
    )
    assert created.status_code == 201, created.text
    pid = created.json()["data"]["project_id"]
    for protocol in ("openai", "anthropic", "vertex"):
        draft = bind_client.post(
            f"/api/v1/projects/{pid}/bindings",
            json={
                "protocol": protocol,
                "supply_mode": "shared",
                "allowed_models": [f"{protocol}-m"],
            },
            headers=_headers(csrf),
        )
        assert draft.status_code == 201, draft.text
        bid = draft.json()["data"]["binding_id"]
        pub = bind_client.post(
            f"/api/v1/projects/{pid}/bindings/{bid}/publish",
            headers=_headers(csrf),
        )
        assert pub.status_code == 200, pub.text
        hint = bind_client.get(f"/api/v1/projects/{pid}/bindings/{bid}/sdk-hint")
        assert hint.status_code == 200
        assert "secret" not in hint.json()["data"]

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    maker = sessionmaker(engine)
    svc = BindingService(
        store=SessionedBindingStore(maker),
        projects=SessionedProjectStore(maker),
        prices=AlwaysPriceLookup(),
    )
    d1 = svc.create(
        project_id=uuid.UUID(pid),
        owner_id=user.id,
        protocol="openai",
        supply_mode="shared",
        role="buyer",
        workspace="buyer",
        request_id="r1",
        allowed_models=["race-a"],
    )
    d2 = svc.create(
        project_id=d1.project_id,
        owner_id=user.id,
        protocol="openai",
        supply_mode="shared",
        role="buyer",
        workspace="buyer",
        request_id="r2",
        allowed_models=["race-b"],
    )

    def _go(bid):
        try:
            svc.publish(
                binding_id=bid,
                owner_id=user.id,
                role="buyer",
                workspace="buyer",
                request_id=str(bid),
            )
            return "ok"
        except BindingError as exc:
            return exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(_go, (d1.binding_id, d2.binding_id)))
        with engine.connect() as conn:
            n = conn.execute(
                text(
                    "SELECT count(*) FROM provider_bindings "
                    "WHERE project_id = CAST(:id AS uuid) "
                    "AND protocol = 'openai' AND status = 'active'"
                ),
                {"id": pid},
            ).scalar_one()
            assert n == 1
    finally:
        engine.dispose()
