"""Fixture routes gated by AUTHORIZATION_FIXTURES_ENABLED + APP_ENV."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.api.v1.authorization import fixtures_enabled
from app.main import app


def test_fixtures_disabled_by_default(monkeypatch: object) -> None:
    monkeypatch.setenv("MODE", "local")  # type: ignore[attr-defined]
    monkeypatch.delenv("AUTHORIZATION_FIXTURES_ENABLED", raising=False)  # type: ignore[attr-defined]
    # resolve_app_mode may be cached indirectly — call fixtures_enabled after env
    assert fixtures_enabled() is False


def test_fixtures_enabled_local_true(monkeypatch: object) -> None:
    monkeypatch.setenv("MODE", "local")  # type: ignore[attr-defined]
    monkeypatch.setenv("AUTHORIZATION_FIXTURES_ENABLED", "true")  # type: ignore[attr-defined]
    assert fixtures_enabled() is True


def test_fixtures_never_in_prod(monkeypatch: object) -> None:
    monkeypatch.setenv("MODE", "prod")  # type: ignore[attr-defined]
    monkeypatch.setenv("AUTHORIZATION_FIXTURES_ENABLED", "true")  # type: ignore[attr-defined]
    assert fixtures_enabled() is False


def test_fixture_create_404_when_disabled(monkeypatch: object) -> None:
    monkeypatch.setenv("MODE", "local")  # type: ignore[attr-defined]
    monkeypatch.delenv("AUTHORIZATION_FIXTURES_ENABLED", raising=False)  # type: ignore[attr-defined]
    client = TestClient(app)
    resp = client.post(
        "/api/v1/authorization/fixtures/resources",
        json={"resource_type": "proxy_key", "action": "proxy_key.create"},
    )
    assert resp.status_code == 404
