"""Unit tests for AuthSettings and auth readiness fail-closed policy (T010)."""

from __future__ import annotations

import secrets

import pytest
from pydantic import ValidationError

from app.config import (
    AuthSettings,
    check_auth_readiness,
    clear_auth_settings_cache,
    load_auth_settings,
)


def _synth_key() -> str:
    return "tm_test_" + secrets.token_urlsafe(32)


def _full_keys(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "session_hmac_key_current": _synth_key(),
        "session_hmac_key_previous": _synth_key(),
        "session_hmac_key_version": 2,
        "otp_hmac_key_current": _synth_key(),
        "otp_hmac_key_previous": "",
        "otp_hmac_key_version": 1,
        "csrf_hmac_key_current": _synth_key(),
        "csrf_hmac_key_previous": _synth_key(),
        "csrf_hmac_key_version": 3,
        "reference_hmac_key_current": _synth_key(),
        "reference_hmac_key_previous": "",
        "reference_hmac_key_version": 1,
        "browser_origins": "https://127.0.0.1:5173,https://app.example.com",
        "trusted_proxy_cidrs": "127.0.0.1/32,::1/128,10.0.0.0/8",
        "sms_adapter": "synthetic",
        "sms_provider_timeout_seconds": 10,
        "dispatcher_lease_seconds": 30,
        "dispatcher_drain_seconds": 15,
        "dispatcher_batch_size": 20,
        "cleanup_batch_size": 500,
        "cleanup_max_runtime_seconds": 900,
        "tls_ready": False,
    }
    base.update(overrides)
    return base


def test_loads_current_and_previous_key_versions() -> None:
    settings = AuthSettings(**_full_keys())  # type: ignore[arg-type]
    session = settings.key_material("session")
    assert session.version == 2
    assert session.current_usable()
    assert session.resolve(2) is not None
    assert session.resolve(1) is not None  # previous
    assert session.resolve(99) is None  # unknown fails closed

    otp = settings.key_material("otp")
    assert otp.version == 1
    assert otp.resolve(1) is not None
    assert otp.resolve(0) is None  # no previous configured


def test_exact_browser_origins_no_wildcard_split() -> None:
    settings = AuthSettings(
        **_full_keys(browser_origins="https://a.example,https://b.example")  # type: ignore[arg-type]
    )
    assert settings.browser_origin_list == [
        "https://a.example",
        "https://b.example",
    ]


def test_trusted_proxy_cidr_list_parsed() -> None:
    settings = AuthSettings(**_full_keys())  # type: ignore[arg-type]
    assert "127.0.0.1/32" in settings.trusted_proxy_cidr_list
    assert "::1/128" in settings.trusted_proxy_cidr_list
    assert "10.0.0.0/8" in settings.trusted_proxy_cidr_list


def test_invalid_trusted_proxy_cidr_rejected() -> None:
    with pytest.raises(ValidationError):
        AuthSettings(**_full_keys(trusted_proxy_cidrs="not-a-cidr"))  # type: ignore[arg-type]


def test_provider_timeout_and_dispatcher_cleanup_params() -> None:
    settings = AuthSettings(
        **_full_keys(  # type: ignore[arg-type]
            sms_provider_timeout_seconds=12,
            dispatcher_lease_seconds=45,
            dispatcher_drain_seconds=20,
            dispatcher_batch_size=50,
            cleanup_batch_size=100,
            cleanup_max_runtime_seconds=600,
        )
    )
    assert settings.sms_provider_timeout_seconds == 12
    assert settings.dispatcher_lease_seconds == 45
    assert settings.dispatcher_drain_seconds == 20
    assert settings.dispatcher_batch_size == 50
    assert settings.cleanup_batch_size == 100
    assert settings.cleanup_max_runtime_seconds == 600


def test_provider_timeout_out_of_range() -> None:
    with pytest.raises(ValidationError):
        AuthSettings(**_full_keys(sms_provider_timeout_seconds=0))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AuthSettings(**_full_keys(sms_provider_timeout_seconds=120))  # type: ignore[arg-type]


def test_local_mode_allows_synthetic_and_placeholder_keys() -> None:
    settings = AuthSettings(
        session_hmac_key_current="replace-me-with-a-generated-session-hmac-key",
        otp_hmac_key_current="replace-me",
        csrf_hmac_key_current="",
        reference_hmac_key_current="",
        sms_adapter="synthetic",
        tls_ready=False,
    )
    result = check_auth_readiness(settings, mode="local")
    assert result.ok is True


def test_prod_missing_tls_fail_closed() -> None:
    settings = AuthSettings(
        **_full_keys(  # type: ignore[arg-type]
            sms_adapter="approved",
            tls_ready=False,
        )
    )
    result = check_auth_readiness(settings, mode="prod")
    assert result.ok is False
    assert any(i.code == "AUTH_TLS_NOT_READY" for i in result.issues)


def test_prod_synthetic_adapter_fail_closed() -> None:
    settings = AuthSettings(
        **_full_keys(  # type: ignore[arg-type]
            sms_adapter="synthetic",
            tls_ready=True,
        )
    )
    result = check_auth_readiness(settings, mode="prod")
    assert result.ok is False
    assert any(i.code == "AUTH_SMS_ADAPTER_NOT_APPROVED" for i in result.issues)


def test_prod_placeholder_keys_fail_closed() -> None:
    settings = AuthSettings(
        **_full_keys(  # type: ignore[arg-type]
            session_hmac_key_current="replace-me-with-a-generated-session-hmac-key",
            sms_adapter="approved",
            tls_ready=True,
        )
    )
    result = check_auth_readiness(settings, mode="prod")
    assert result.ok is False
    assert any(i.code == "AUTH_KEY_MISSING" for i in result.issues)


def test_prod_ready_when_fully_configured() -> None:
    settings = AuthSettings(
        **_full_keys(  # type: ignore[arg-type]
            sms_adapter="approved",
            tls_ready=True,
        )
    )
    result = check_auth_readiness(settings, mode="prod")
    assert result.ok is True
    assert result.issues == ()


def test_test_mode_also_requires_tls_and_approved_adapter() -> None:
    settings = AuthSettings(**_full_keys(sms_adapter="synthetic", tls_ready=False))  # type: ignore[arg-type]
    result = check_auth_readiness(settings, mode="test")
    assert result.ok is False


def test_load_auth_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_settings_cache()
    key = _synth_key()
    monkeypatch.setenv("AUTH_SESSION_HMAC_KEY_CURRENT", key)
    monkeypatch.setenv("AUTH_SESSION_HMAC_KEY_VERSION", "5")
    monkeypatch.setenv("AUTH_OTP_HMAC_KEY_CURRENT", key)
    monkeypatch.setenv("AUTH_CSRF_HMAC_KEY_CURRENT", key)
    monkeypatch.setenv("AUTH_REFERENCE_HMAC_KEY_CURRENT", key)
    monkeypatch.setenv("AUTH_BROWSER_ORIGINS", "https://127.0.0.1:5173")
    monkeypatch.setenv("AUTH_TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    monkeypatch.setenv("AUTH_SMS_ADAPTER", "synthetic")
    monkeypatch.setenv("AUTH_TLS_READY", "false")
    settings = load_auth_settings()
    assert settings.session_hmac_key_version == 5
    assert settings.session_hmac_key_current == key
    assert settings.browser_origin_list == ["https://127.0.0.1:5173"]
    clear_auth_settings_cache()
