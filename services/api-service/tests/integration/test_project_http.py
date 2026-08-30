"""Project HTTP against migrated PostgreSQL."""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache
from app.domain.projects.service import ProjectError, ProjectService
from app.domain.users.models import UserRole
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.repositories.projects import SessionedProjectStore
from app.sms.synthetic import SyntheticSmsAdapter
from tests.integration.test_session_lifecycle import _login_client

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_proj_" + "x" * 40


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
def proj_client(
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


def test_create_archive_admission_and_idor(
    proj_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    owner = account_factory.create_active(role=UserRole.buyer)
    csrf = _login_client(proj_client, owner.phone_normalized, auth_migrated_postgres)
    created = proj_client.post(
        "/api/v1/projects",
        json={
            "display_name": "LiveOne",
            "mode": "dedicated",
            "enabled_protocols": ["openai"],
        },
        headers=_headers(csrf),
    )
    assert created.status_code == 201, created.text
    pid = created.json()["data"]["project_id"]
    assert created.json()["data"]["mode"] == "dedicated"
    patched = proj_client.patch(
        f"/api/v1/projects/{pid}",
        json={"mode": "shared"},
        headers=_headers(csrf),
    )
    assert patched.status_code == 400
    assert patched.json()["code"] == "MODE_IMMUTABLE"
    assert (
        proj_client.post(
            f"/api/v1/projects/{pid}/activate", headers=_headers(csrf)
        ).status_code
        == 200
    )
    start = time.monotonic()
    assert (
        proj_client.post(
            f"/api/v1/projects/{pid}/archive", headers=_headers(csrf)
        ).status_code
        == 200
    )
    adm = proj_client.get(f"/api/v1/projects/{pid}/admission")
    assert time.monotonic() - start < 1.0
    assert adm.json()["data"]["allows_new_proxy"] is False

    other = account_factory.create_active(role=UserRole.buyer)
    other_client = TestClient(app)
    with other_client:
        other_client.app.state.rate_limiter = MemoryRateLimiter()
        other_client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        other_client.app.state.sms_adapter = SyntheticSmsAdapter()
        _login_client(other_client, other.phone_normalized, auth_migrated_postgres)
        foreign = other_client.get(f"/api/v1/projects/{pid}")
        missing = other_client.get(f"/api/v1/projects/{uuid.uuid4()}")
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json()["code"] == missing.json()["code"] == "NOT_FOUND"
        assert foreign.json()["message"] == missing.json()["message"]


def test_seller_workspace_cannot_create(
    proj_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(role=UserRole.both)
    csrf = _login_client(proj_client, user.phone_normalized, auth_migrated_postgres)
    switched = proj_client.post(
        "/api/v1/auth/workspace",
        json={"workspace": "seller"},
        headers=_headers(csrf),
    )
    assert switched.status_code == 200
    res = proj_client.post(
        "/api/v1/projects",
        json={
            "display_name": "SellerNo",
            "mode": "shared",
            "enabled_protocols": ["openai"],
        },
        headers=_headers(csrf),
    )
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN_ROLE"


def test_csrf_required_for_create(
    proj_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(role=UserRole.buyer)
    _login_client(proj_client, user.phone_normalized, auth_migrated_postgres)
    res = proj_client.post(
        "/api/v1/projects",
        json={
            "display_name": "NoCsrf",
            "mode": "shared",
            "enabled_protocols": ["openai"],
        },
        headers={"Origin": ORIGIN},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "CSRF_INVALID"


def test_sql_mode_trigger_and_concurrent_names(
    proj_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    owner = account_factory.create_active(role=UserRole.buyer)
    csrf = _login_client(proj_client, owner.phone_normalized, auth_migrated_postgres)
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    maker = sessionmaker(engine)
    svc = ProjectService(store=SessionedProjectStore(maker))

    def _race(suffix: str) -> str:
        try:
            svc.create(
                owner_id=owner.id,
                display_name="RaceName",
                mode="shared",
                enabled_protocols=["openai"],
                role="buyer",
                workspace="buyer",
                request_id=suffix,
                idempotency_key=suffix,
            )
            return "ok"
        except ProjectError as exc:
            return exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(_race, ("k-a", "k-b")))
        assert "ok" in outcomes
        assert outcomes.count("ok") == 1
        assert "NAME_CONFLICT" in outcomes

        created = proj_client.post(
            "/api/v1/projects",
            json={
                "display_name": "TriggerMe",
                "mode": "shared",
                "enabled_protocols": ["vertex"],
            },
            headers=_headers(csrf),
        )
        pid = created.json()["data"]["project_id"]
        with engine.connect() as conn:
            with pytest.raises(Exception):
                with conn.begin():
                    conn.execute(
                        text(
                            "UPDATE projects SET mode = 'dedicated' "
                            "WHERE id = CAST(:id AS uuid)"
                        ),
                        {"id": pid},
                    )
        with engine.connect() as conn:
            mode = conn.execute(
                text("SELECT mode FROM projects WHERE id = CAST(:id AS uuid)"),
                {"id": pid},
            ).scalar_one()
            assert mode == "shared"
    finally:
        engine.dispose()
