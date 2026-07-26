"""Auth challenge rolling rate limit: dual ZSET Lua, HMAC refs, fail-closed.

Separate from registration's fixed-window ``rate_limit.py`` (FR-008 / Decision 10).
Each new idempotency winner counts once; replays must not call this path.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from redis.asyncio import Redis

from app.rate_limit import RateLimitBackendUnavailable

# Defaults per FR-008
AUTH_PHONE_LIMIT = 5
AUTH_IP_LIMIT = 20
AUTH_WINDOW_SECONDS = 3600  # rolling 1 hour
AUTH_TTL_SECONDS = 3700  # slightly > window

_LUA_PATH = Path(__file__).resolve().parent / "domain" / "authentication" / "rate_limit.lua"
_LUA_SCRIPT: str | None = None


def load_auth_rate_limit_lua() -> str:
    """Load committed Lua script bytes (cached after first read)."""
    global _LUA_SCRIPT
    if _LUA_SCRIPT is None:
        _LUA_SCRIPT = _LUA_PATH.read_text(encoding="utf-8")
    return _LUA_SCRIPT


def auth_rate_limit_key(env: str, dimension: str, ref_hex: str) -> str:
    """Build Redis key; never embed raw phone or IP."""
    if dimension not in ("phone", "ip"):
        raise ValueError("dimension must be phone or ip")
    safe_env = env.replace(":", "_")[:32] or "local"
    return f"tm:{safe_env}:auth:v1:otp:rl:{dimension}:{ref_hex}"


def ref_to_hex(ref: bytes) -> str:
    return ref.hex()


@dataclass(frozen=True)
class AuthRateLimitDecision:
    allowed: bool
    dimension: str | None = None  # "phone" | "ip" — never exposed to clients
    retry_after_seconds: int = 1
    phone_count: int = 0
    ip_count: int = 0


class AuthRateLimiter(Protocol):
    async def check_and_increment(
        self,
        *,
        phone_ref: bytes,
        ip_ref: bytes,
        member_id: str | None = None,
    ) -> AuthRateLimitDecision: ...

    async def close(self) -> None: ...


class RedisAuthRateLimiter:
    """Phone 5/hour + IP 20/hour rolling windows via single atomic Lua."""

    def __init__(
        self,
        redis: Redis,
        *,
        env: str = "local",
        phone_limit: int = AUTH_PHONE_LIMIT,
        ip_limit: int = AUTH_IP_LIMIT,
        window_seconds: int = AUTH_WINDOW_SECONDS,
        ttl_seconds: int = AUTH_TTL_SECONDS,
        lua_script: str | None = None,
    ) -> None:
        self._redis = redis
        self._env = env
        self._phone_limit = phone_limit
        self._ip_limit = ip_limit
        self._window_ms = window_seconds * 1000
        self._ttl = ttl_seconds
        self._script = lua_script if lua_script is not None else load_auth_rate_limit_lua()
        self._sha: str | None = None

    async def _eval(
        self, keys: list[str], args: list[str | int]
    ) -> list[object]:
        try:
            if self._sha is None:
                self._sha = await self._redis.script_load(self._script)
            try:
                result = await self._redis.evalsha(self._sha, len(keys), *keys, *args)
            except Exception as exc:  # NOSCRIPT or similar — reload once
                if "NOSCRIPT" not in str(exc).upper():
                    raise
                self._sha = await self._redis.script_load(self._script)
                result = await self._redis.evalsha(self._sha, len(keys), *keys, *args)
            return list(result)  # type: ignore[arg-type]
        except RateLimitBackendUnavailable:
            raise
        except Exception as exc:
            raise RateLimitBackendUnavailable from exc

    async def check_and_increment(
        self,
        *,
        phone_ref: bytes,
        ip_ref: bytes,
        member_id: str | None = None,
    ) -> AuthRateLimitDecision:
        if not phone_ref or not ip_ref:
            raise ValueError("phone_ref and ip_ref are required")
        member = member_id or str(uuid.uuid4())
        phone_key = auth_rate_limit_key(self._env, "phone", ref_to_hex(phone_ref))
        ip_key = auth_rate_limit_key(self._env, "ip", ref_to_hex(ip_ref))
        # Fail closed: never skip Lua when Redis is unreachable.
        raw = await self._eval(
            [phone_key, ip_key],
            [
                member,
                self._phone_limit,
                self._ip_limit,
                self._window_ms,
                self._ttl,
            ],
        )
        allowed = int(raw[0]) == 1
        dimension = str(raw[1]) if raw[1] else None
        retry_after = max(1, int(raw[2])) if not allowed else 0
        phone_count = int(raw[3])
        ip_count = int(raw[4])
        return AuthRateLimitDecision(
            allowed=allowed,
            dimension=dimension if not allowed else None,
            retry_after_seconds=retry_after if not allowed else 1,
            phone_count=phone_count,
            ip_count=ip_count,
        )

    async def close(self) -> None:
        await self._redis.aclose()


class MemoryAuthRateLimiter:
    """In-process dual counter for unit/integration tests (not multi-worker safe)."""

    def __init__(
        self,
        *,
        phone_limit: int = AUTH_PHONE_LIMIT,
        ip_limit: int = AUTH_IP_LIMIT,
        fail: bool = False,
        retry_after_seconds: int = 60,
    ) -> None:
        self._phone_limit = phone_limit
        self._ip_limit = ip_limit
        self._fail = fail
        self._retry_after = retry_after_seconds
        self._phone: dict[bytes, int] = {}
        self._ip: dict[bytes, int] = {}
        self.members: list[str] = []

    async def check_and_increment(
        self,
        *,
        phone_ref: bytes,
        ip_ref: bytes,
        member_id: str | None = None,
    ) -> AuthRateLimitDecision:
        if self._fail:
            raise RateLimitBackendUnavailable("simulated auth rate-limit backend down")
        phone_count = self._phone.get(phone_ref, 0)
        ip_count = self._ip.get(ip_ref, 0)
        if phone_count >= self._phone_limit:
            return AuthRateLimitDecision(
                allowed=False,
                dimension="phone",
                retry_after_seconds=self._retry_after,
                phone_count=phone_count,
                ip_count=ip_count,
            )
        if ip_count >= self._ip_limit:
            return AuthRateLimitDecision(
                allowed=False,
                dimension="ip",
                retry_after_seconds=self._retry_after,
                phone_count=phone_count,
                ip_count=ip_count,
            )
        member = member_id or str(uuid.uuid4())
        self.members.append(member)
        self._phone[phone_ref] = phone_count + 1
        self._ip[ip_ref] = ip_count + 1
        return AuthRateLimitDecision(
            allowed=True,
            phone_count=phone_count + 1,
            ip_count=ip_count + 1,
        )

    async def close(self) -> None:
        return None


def build_auth_rate_limiter_from_env() -> AuthRateLimiter | None:
    """Return Redis auth limiter if REDIS_URL set; None means unconfigured."""
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    env = (
        os.environ.get("MODE")
        or os.environ.get("APP_ENV")
        or "local"
    ).strip().lower() or "local"
    client = Redis.from_url(url, decode_responses=True)
    return RedisAuthRateLimiter(client, env=env)
