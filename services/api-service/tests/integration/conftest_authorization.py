"""Authorization integration fixtures: session cookies, roles, revoke helpers."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache, load_auth_settings
from app.domain.authorization.workspace import default_workspace
from app.domain.users.models import User, UserRole
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.security.csrf import issue_csrf_token
from app.security.session import (
    SESSION_COOKIE_NAME,
    generate_session_token,
    token_digest,
)
from app.sms.synthetic import SyntheticSmsAdapter

pytest_plugins: list[str] = []  # registered from tests/conftest.py

ORIGIN = "https://127.0.0.1:5173"
_AUTHZ_KEY = "tm_authz_int_" + secrets.token_urlsafe(32)


def _authz_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("MODE", "local")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("AUTHORIZATION_FIXTURES_ENABLED", "true")
    monkeypatch.setenv("AUTH_SESSION_HMAC_KEY_CURRENT", _AUTHZ_KEY)
    monkeypatch.setenv("AUTH_OTP_HMAC_KEY_CURRENT", _AUTHZ_KEY)
    monkeypatch.setenv("AUTH_CSRF_HMAC_KEY_CURRENT", _AUTHZ_KEY)
    monkeypatch.setenv("AUTH_REFERENCE_HMAC_KEY_CURRENT", _AUTHZ_KEY)
    monkeypatch.setenv("AUTH_BROWSER_ORIGINS", ORIGIN)
    monkeypatch.setenv("AUTH_SMS_ADAPTER", "synthetic")
    monkeypatch.setenv("AUTH_DISPATCHER_ENABLED", "0")
    clear_auth_settings_cache()


@dataclass
class IssuedSession:
    user: User
    cookie_value: str
    session_id: uuid.UUID
    csrf_token: str


class AuthzSessionFactory:
    """Issue and revoke opaque sessions without OTP round-trip."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url, pool_pre_ping=True)
        self._factory = sessionmaker(
            self._engine, class_=Session, expire_on_commit=False
        )

    def close(self) -> None:
        self._engine.dispose()

    def issue(self, user: User, *, workspace: str | None = None) -> IssuedSession:
        settings = load_auth_settings()
        session_mat = settings.key_material("session")
        csrf_mat = settings.key_material("csrf")
        token = generate_session_token(session_mat.version)
        digest = token_digest(session_mat.current, token.opaque_secret)
        session_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
        ws = workspace if workspace is not None else default_workspace(role_value)
        with self._factory() as db:
            # revoke any existing active session for user (partial unique)
            db.execute(
                text(
                    "UPDATE auth_sessions SET revoked_at = :now, "
                    "revocation_reason = 'superseded' "
                    "WHERE user_id = CAST(:uid AS uuid) AND revoked_at IS NULL"
                ),
                {"now": now, "uid": str(user.id)},
            )
            db.execute(
                text(
                    "INSERT INTO auth_sessions ("
                    "id, user_id, token_digest, token_key_version, role_snapshot, "
                    "workspace, issued_at, expires_at, revoked_at, revocation_reason, "
                    "created_request_id, delete_after"
                    ") VALUES ("
                    "CAST(:id AS uuid), CAST(:uid AS uuid), :digest, :ver, "
                    "CAST(:role AS user_role), :workspace, :issued, :expires, "
                    "NULL, NULL, :req, :delete_after"
                    ")"
                ),
                {
                    "id": str(session_id),
                    "uid": str(user.id),
                    "digest": digest,
                    "ver": session_mat.version,
                    "role": role_value,
                    "workspace": ws,
                    "issued": now,
                    "expires": now + timedelta(hours=1),
                    "req": "authz-test",
                    "delete_after": now + timedelta(days=2),
                },
            )
            db.commit()
        csrf = issue_csrf_token(csrf_mat.current, csrf_mat.version, session_id)
        return IssuedSession(
            user=user,
            cookie_value=token.cookie_value,
            session_id=session_id,
            csrf_token=csrf,
        )

    def revoke(self, session_id: uuid.UUID, *, reason: str = "logout") -> None:
        now = datetime.now(timezone.utc)
        with self._factory() as db:
            db.execute(
                text(
                    "UPDATE auth_sessions SET revoked_at = :now, "
                    "revocation_reason = :reason "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"now": now, "reason": reason, "id": str(session_id)},
            )
            db.commit()

    def set_user_role(self, user_id: uuid.UUID, role: UserRole | str) -> None:
        role_value = role.value if hasattr(role, "value") else str(role)
        with self._factory() as db:
            db.execute(
                text(
                    "UPDATE users SET role = CAST(:role AS user_role), "
                    "updated_at = NOW() WHERE id = CAST(:id AS uuid)"
                ),
                {"role": role_value, "id": str(user_id)},
            )
            db.commit()

    def set_workspace(self, session_id: uuid.UUID, workspace: str) -> None:
        with self._factory() as db:
            db.execute(
                text(
                    "UPDATE auth_sessions SET workspace = :ws "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"ws": workspace, "id": str(session_id)},
            )
            db.commit()


def force_session_cookie(client: TestClient, value: str) -> None:
    try:
        client.cookies.jar.clear()
    except Exception:  # noqa: BLE001
        client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, value, path="/")


def authz_headers(issued: IssuedSession, *, with_csrf: bool = True) -> dict[str, str]:
    headers = {"Origin": ORIGIN, "X-Request-ID": str(uuid.uuid4())}
    if with_csrf:
        headers["X-CSRF-Token"] = issued.csrf_token
    return headers


@pytest.fixture
def authz_client(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    _authz_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        client.app.state.sms_adapter = SyntheticSmsAdapter()
        yield client
    clear_auth_settings_cache()


@pytest.fixture
def authz_sessions(
    auth_migrated_postgres: str,
) -> Iterator[AuthzSessionFactory]:
    factory = AuthzSessionFactory(auth_migrated_postgres)
    try:
        yield factory
    finally:
        factory.close()
