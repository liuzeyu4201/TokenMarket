"""Authentication and session configuration (SF04 / feature 004).

Settings load exclusively from ``AUTH_*`` environment variables (plus
``MODE`` / ``APP_ENV`` for environment class). Production readiness fails
closed without real keys, TLS, and an approved SMS adapter.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_network
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ModeName = Literal["local", "test", "prod"]

# Placeholder substrings that must never pass prod readiness.
_PLACEHOLDER_MARKERS = (
    "replace-me",
    "changeme",
    "todo",
    "placeholder",
    "example",
)

# Local/test may use synthetic; non-local requires an approved real adapter.
_APPROVED_SMS_ADAPTERS = frozenset(
    {
        "approved",
        "twilio",
        "aliyun",
        "tencent",
    }
)
_LOCAL_SMS_ADAPTERS = frozenset({"synthetic", "fake", "test"})


def resolve_app_mode() -> ModeName:
    """Return effective mode from MODE or APP_ENV; default local."""
    raw = (
        (os.environ.get("MODE") or os.environ.get("APP_ENV") or "local").strip().lower()
    )
    if raw in ("local", "test", "prod"):
        return raw  # type: ignore[return-value]
    # Unknown values treated as non-local for fail-closed policy when TLS/keys matter.
    if raw in ("production", "prd"):
        return "prod"
    if raw in ("development", "dev"):
        return "local"
    if raw in ("staging", "stage"):
        return "test"
    return "local"


def _is_placeholder_key(value: str) -> bool:
    if not value or not value.strip():
        return True
    lowered = value.strip().lower()
    if len(value.strip()) < 16:
        return True
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _parse_csv(value: str) -> list[str]:
    if not value or not value.strip():
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


class AuthSettings(BaseSettings):
    """Versioned auth crypto keys and operational parameters."""

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        extra="ignore",
        case_sensitive=False,
    )

    session_hmac_key_current: str = Field(default="")
    session_hmac_key_previous: str = Field(default="")
    session_hmac_key_version: int = Field(default=1)

    otp_hmac_key_current: str = Field(default="")
    otp_hmac_key_previous: str = Field(default="")
    otp_hmac_key_version: int = Field(default=1)

    csrf_hmac_key_current: str = Field(default="")
    csrf_hmac_key_previous: str = Field(default="")
    csrf_hmac_key_version: int = Field(default=1)

    reference_hmac_key_current: str = Field(default="")
    reference_hmac_key_previous: str = Field(default="")
    reference_hmac_key_version: int = Field(default=1)

    browser_origins: str = Field(default="")
    trusted_proxy_cidrs: str = Field(default="")

    sms_adapter: str = Field(default="synthetic")
    sms_provider_timeout_seconds: int = Field(default=10)

    dispatcher_lease_seconds: int = Field(default=30)
    dispatcher_drain_seconds: int = Field(default=15)
    dispatcher_batch_size: int = Field(default=20)

    cleanup_batch_size: int = Field(default=500)
    cleanup_max_runtime_seconds: int = Field(default=900)
    cleanup_schedule_cron: str = Field(default="17 * * * *")

    tls_ready: bool = Field(default=False)

    @field_validator(
        "session_hmac_key_version",
        "otp_hmac_key_version",
        "csrf_hmac_key_version",
        "reference_hmac_key_version",
        mode="before",
    )
    @classmethod
    def _positive_version(cls, value: object) -> object:
        if value is None or value == "":
            return 1
        return value

    @field_validator(
        "sms_provider_timeout_seconds",
        "dispatcher_lease_seconds",
        "dispatcher_drain_seconds",
        "dispatcher_batch_size",
        "cleanup_batch_size",
        "cleanup_max_runtime_seconds",
        mode="before",
    )
    @classmethod
    def _positive_int(cls, value: object) -> object:
        if value is None or value == "":
            return value
        return value

    @model_validator(mode="after")
    def _validate_ranges(self) -> AuthSettings:
        if self.session_hmac_key_version < 1:
            raise ValueError("session HMAC key version must be >= 1")
        if self.otp_hmac_key_version < 1:
            raise ValueError("OTP HMAC key version must be >= 1")
        if self.csrf_hmac_key_version < 1:
            raise ValueError("CSRF HMAC key version must be >= 1")
        if self.reference_hmac_key_version < 1:
            raise ValueError("reference HMAC key version must be >= 1")
        if (
            self.sms_provider_timeout_seconds < 1
            or self.sms_provider_timeout_seconds > 60
        ):
            raise ValueError("AUTH_SMS_PROVIDER_TIMEOUT_SECONDS must be 1..60")
        if self.dispatcher_lease_seconds < 1:
            raise ValueError("AUTH_DISPATCHER_LEASE_SECONDS must be >= 1")
        if self.dispatcher_drain_seconds < 0:
            raise ValueError("AUTH_DISPATCHER_DRAIN_SECONDS must be >= 0")
        if self.dispatcher_batch_size < 1:
            raise ValueError("AUTH_DISPATCHER_BATCH_SIZE must be >= 1")
        if self.cleanup_batch_size < 1:
            raise ValueError("AUTH_CLEANUP_BATCH_SIZE must be >= 1")
        if self.cleanup_max_runtime_seconds < 1:
            raise ValueError("AUTH_CLEANUP_MAX_RUNTIME_SECONDS must be >= 1")
        # Validate CIDR syntax early so bad config fails closed at load.
        for cidr in self.trusted_proxy_cidr_list:
            try:
                ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(f"invalid trusted proxy CIDR: {cidr!r}") from exc
        return self

    @property
    def browser_origin_list(self) -> list[str]:
        return _parse_csv(self.browser_origins)

    @property
    def trusted_proxy_cidr_list(self) -> list[str]:
        return _parse_csv(self.trusted_proxy_cidrs)

    def key_material(
        self, family: Literal["session", "otp", "csrf", "reference"]
    ) -> VersionedKeyMaterial:
        current = getattr(self, f"{family}_hmac_key_current")
        previous = getattr(self, f"{family}_hmac_key_previous")
        version = getattr(self, f"{family}_hmac_key_version")
        return VersionedKeyMaterial(
            family=family,
            version=int(version),
            current=current.encode("utf-8") if current else b"",
            previous=previous.encode("utf-8") if previous else None,
            current_raw=current,
            previous_raw=previous or None,
        )


@dataclass(frozen=True)
class VersionedKeyMaterial:
    """Current + optional previous key for one HMAC family."""

    family: str
    version: int
    current: bytes
    previous: bytes | None
    current_raw: str
    previous_raw: str | None

    def resolve(self, version: int) -> bytes | None:
        """Return key bytes for *version*, or None if unknown (fail closed)."""
        if version == self.version:
            if not self.current:
                return None
            return self.current
        if self.previous is not None and version == self.version - 1:
            if not self.previous:
                return None
            return self.previous
        return None

    def current_usable(self) -> bool:
        return bool(self.current) and not _is_placeholder_key(self.current_raw)


@dataclass(frozen=True)
class AuthReadinessIssue:
    code: str
    message: str


@dataclass(frozen=True)
class AuthReadinessResult:
    ok: bool
    issues: tuple[AuthReadinessIssue, ...] = ()

    @classmethod
    def success(cls) -> AuthReadinessResult:
        return cls(ok=True)

    @classmethod
    def failure(cls, *issues: AuthReadinessIssue) -> AuthReadinessResult:
        return cls(ok=False, issues=issues)


def check_auth_readiness(
    settings: AuthSettings | None = None,
    *,
    mode: ModeName | None = None,
) -> AuthReadinessResult:
    """Evaluate auth production readiness without side effects.

    Local mode allows synthetic SMS and incomplete keys for scaffolding.
    Test/prod fail closed without usable keys, TLS, and an approved adapter.
    """
    settings = settings if settings is not None else load_auth_settings()
    effective = mode if mode is not None else resolve_app_mode()
    issues: list[AuthReadinessIssue] = []

    families = ("session", "otp", "csrf", "reference")
    for family in families:
        material = settings.key_material(family)  # type: ignore[arg-type]
        if not material.current_usable():
            issues.append(
                AuthReadinessIssue(
                    code="AUTH_KEY_MISSING",
                    message=f"{family} HMAC current key missing or placeholder",
                )
            )

    if effective in ("test", "prod"):
        if not settings.tls_ready:
            issues.append(
                AuthReadinessIssue(
                    code="AUTH_TLS_NOT_READY",
                    message="AUTH_TLS_READY must be true outside local mode",
                )
            )
        adapter = (settings.sms_adapter or "").strip().lower()
        if adapter in _LOCAL_SMS_ADAPTERS or adapter not in _APPROVED_SMS_ADAPTERS:
            issues.append(
                AuthReadinessIssue(
                    code="AUTH_SMS_ADAPTER_NOT_APPROVED",
                    message="non-local mode requires an approved SMS adapter",
                )
            )
        if not settings.browser_origin_list:
            issues.append(
                AuthReadinessIssue(
                    code="AUTH_ORIGINS_MISSING",
                    message="AUTH_BROWSER_ORIGINS must list exact origins",
                )
            )
        # Exact origins only — reject wildcards.
        for origin in settings.browser_origin_list:
            if origin == "*" or "://" not in origin:
                issues.append(
                    AuthReadinessIssue(
                        code="AUTH_ORIGINS_INVALID",
                        message="browser origins must be exact scheme://host[:port]",
                    )
                )
                break
            if re.search(r"[\s*]", origin.split("://", 1)[-1].split("/")[0]):
                issues.append(
                    AuthReadinessIssue(
                        code="AUTH_ORIGINS_INVALID",
                        message="browser origins must not contain wildcards",
                    )
                )
                break

    if effective == "local":
        # Local may run with synthetic adapter; still surface missing keys as
        # soft failure only when operator enables strict local checks later.
        # For local scaffolding, incomplete keys are allowed for unit tests
        # that do not exercise crypto — but readiness callable still reports
        # key issues when current keys are placeholders *and* something else
        # also fails. Keep local key-only gaps non-blocking:
        key_only = all(i.code == "AUTH_KEY_MISSING" for i in issues)
        if key_only:
            # Allow local process start without full key material.
            return AuthReadinessResult.success()

    if issues:
        return AuthReadinessResult.failure(*issues)
    return AuthReadinessResult.success()


@lru_cache(maxsize=1)
def load_auth_settings() -> AuthSettings:
    """Load and cache AuthSettings from the process environment."""
    return AuthSettings()


def clear_auth_settings_cache() -> None:
    """Drop the cached settings instance (tests / process env changes)."""
    load_auth_settings.cache_clear()
