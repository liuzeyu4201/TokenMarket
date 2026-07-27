"""Registration rate limiting: Redis fixed window, fail-closed if Redis down."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis

# Defaults per FR-019
IP_LIMIT = 20
PHONE_LIMIT = 5
WINDOW_SECONDS = 900  # 15 minutes


class RateLimitBackendUnavailable(Exception):
    """Redis (or rate-limit backend) is not usable — fail closed."""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    dimension: str | None = None  # "ip" | "phone" — not exposed to clients


class RateLimiter(Protocol):
    async def check_and_increment(
        self, *, ip: str, phone_normalized: str | None
    ) -> RateLimitDecision: ...

    async def close(self) -> None: ...


class RedisRateLimiter:
    """IP always counted; phone counted only when phone_normalized is set."""

    def __init__(
        self,
        redis: Redis,
        *,
        ip_limit: int = IP_LIMIT,
        phone_limit: int = PHONE_LIMIT,
        window_seconds: int = WINDOW_SECONDS,
    ) -> None:
        self._redis = redis
        self._ip_limit = ip_limit
        self._phone_limit = phone_limit
        self._window = window_seconds

    async def check_and_increment(
        self, *, ip: str, phone_normalized: str | None
    ) -> RateLimitDecision:
        try:
            ip_key = f"reg:rl:ip:{ip}"
            ip_count = await self._incr_window(ip_key)
            if ip_count > self._ip_limit:
                return RateLimitDecision(allowed=False, dimension="ip")

            if phone_normalized is not None:
                phone_key = f"reg:rl:phone:{phone_normalized}"
                phone_count = await self._incr_window(phone_key)
                if phone_count > self._phone_limit:
                    return RateLimitDecision(allowed=False, dimension="phone")

            return RateLimitDecision(allowed=True)
        except Exception as exc:  # fail closed — no unlimited writes
            raise RateLimitBackendUnavailable from exc

    async def _incr_window(self, key: str) -> int:
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self._window, nx=True)
        results = await pipe.execute()
        return int(results[0])

    async def close(self) -> None:
        await self._redis.aclose()


class MemoryRateLimiter:
    """In-process limiter for unit tests (not multi-worker safe)."""

    def __init__(
        self,
        *,
        ip_limit: int = IP_LIMIT,
        phone_limit: int = PHONE_LIMIT,
        fail: bool = False,
    ) -> None:
        self._ip_limit = ip_limit
        self._phone_limit = phone_limit
        self._fail = fail
        self._ip: dict[str, int] = {}
        self._phone: dict[str, int] = {}

    async def check_and_increment(
        self, *, ip: str, phone_normalized: str | None
    ) -> RateLimitDecision:
        if self._fail:
            raise RateLimitBackendUnavailable("simulated")
        self._ip[ip] = self._ip.get(ip, 0) + 1
        if self._ip[ip] > self._ip_limit:
            return RateLimitDecision(allowed=False, dimension="ip")
        if phone_normalized is not None:
            self._phone[phone_normalized] = self._phone.get(phone_normalized, 0) + 1
            if self._phone[phone_normalized] > self._phone_limit:
                return RateLimitDecision(allowed=False, dimension="phone")
        return RateLimitDecision(allowed=True)

    async def close(self) -> None:
        return None


def build_rate_limiter_from_env() -> RateLimiter | None:
    """Return Redis limiter if REDIS_URL set; None means unconfigured
    (fail closed on use).
    """
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    client = Redis.from_url(url, decode_responses=True)
    return RedisRateLimiter(client)
