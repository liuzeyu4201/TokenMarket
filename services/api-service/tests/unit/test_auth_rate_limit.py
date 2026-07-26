"""Unit tests: auth Redis Lua rolling rate limiter (T055 / US2)."""

from __future__ import annotations

import secrets
from typing import Any

import pytest

from app.auth_rate_limit import (
    AUTH_IP_LIMIT,
    AUTH_PHONE_LIMIT,
    AUTH_TTL_SECONDS,
    AUTH_WINDOW_SECONDS,
    MemoryAuthRateLimiter,
    RedisAuthRateLimiter,
    auth_rate_limit_key,
    load_auth_rate_limit_lua,
    ref_to_hex,
)
from app.observability import AUTH_RATE_LIMITED_TOTAL, record_auth_rate_limited
from app.rate_limit import RateLimitBackendUnavailable
from app.security.reference import ip_ref, phone_ref


class FakeAsyncRedis:
    """Minimal async Redis supporting script_load, evalsha, TIME, ZSET ops."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.scripts: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.ttls: dict[str, int] = {}
        self._now_s = 1_700_000_000
        self._now_us = 0

    def advance_ms(self, ms: int) -> None:
        self._now_s += ms // 1000
        self._now_us += (ms % 1000) * 1000
        if self._now_us >= 1_000_000:
            self._now_s += self._now_us // 1_000_000
            self._now_us %= 1_000_000

    async def script_load(self, script: str) -> str:
        if self.fail:
            raise ConnectionError("redis down")
        sha = secrets.token_hex(20)
        self.scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> list[Any]:
        if self.fail:
            raise ConnectionError("redis down")
        if sha not in self.scripts:
            raise Exception("NOSCRIPT No matching script")
        keys = list(keys_and_args[:numkeys])
        args = list(keys_and_args[numkeys:])
        return self._run_lua(keys, args)

    def _run_lua(self, keys: list[Any], args: list[Any]) -> list[Any]:
        """Subset interpreter matching rate_limit.lua semantics."""
        phone_key, ip_key = str(keys[0]), str(keys[1])
        member = str(args[0])
        phone_limit = int(args[1])
        ip_limit = int(args[2])
        window_ms = int(args[3])
        ttl_seconds = int(args[4])
        now_ms = self._now_s * 1000 + self._now_us // 1000
        cutoff = now_ms - window_ms

        def prune(key: str) -> None:
            z = self.zsets.setdefault(key, {})
            dead = [m for m, s in z.items() if s <= cutoff]
            for m in dead:
                del z[m]

        prune(phone_key)
        prune(ip_key)
        phone_count = len(self.zsets.get(phone_key, {}))
        ip_count = len(self.zsets.get(ip_key, {}))

        def retry_after(key: str) -> int:
            z = self.zsets.get(key, {})
            if not z:
                return 1
            oldest = min(z.values())
            remain_ms = (oldest + window_ms) - now_ms
            if remain_ms <= 0:
                return 1
            return max(1, (remain_ms + 999) // 1000)

        if phone_count >= phone_limit:
            return [0, "phone", retry_after(phone_key), phone_count, ip_count]
        if ip_count >= ip_limit:
            return [0, "ip", retry_after(ip_key), phone_count, ip_count]

        self.zsets.setdefault(phone_key, {})[member] = float(now_ms)
        self.zsets.setdefault(ip_key, {})[member] = float(now_ms)
        self.ttls[phone_key] = ttl_seconds
        self.ttls[ip_key] = ttl_seconds
        return [1, "", 0, phone_count + 1, ip_count + 1]

    async def aclose(self) -> None:
        return None


def test_lua_script_is_committed_and_dual_zset() -> None:
    script = load_auth_rate_limit_lua()
    assert "ZREMRANGEBYSCORE" in script
    assert "ZADD" in script
    assert "TIME" in script
    assert "phone" in script
    assert "ip" in script


def test_key_shape_uses_hmac_hex_not_raw() -> None:
    key = b"tm_ref_" + b"k" * 32
    phone = "13800138000"
    ip = "203.0.113.9"
    p = phone_ref(key, phone)
    i = ip_ref(key, ip)
    p_key = auth_rate_limit_key("local", "phone", ref_to_hex(p))
    i_key = auth_rate_limit_key("local", "ip", ref_to_hex(i))
    assert phone not in p_key
    assert ip not in i_key
    assert p_key.startswith("tm:local:auth:v1:otp:rl:phone:")
    assert i_key.startswith("tm:local:auth:v1:otp:rl:ip:")
    assert ref_to_hex(p) in p_key


@pytest.mark.asyncio
async def test_phone_limit_five_per_hour() -> None:
    fake = FakeAsyncRedis()
    lim = RedisAuthRateLimiter(
        fake,  # type: ignore[arg-type]
        env="test",
        phone_limit=AUTH_PHONE_LIMIT,
        ip_limit=100,
    )
    phone = secrets.token_bytes(32)
    ip = secrets.token_bytes(32)
    for n in range(5):
        d = await lim.check_and_increment(
            phone_ref=phone, ip_ref=ip, member_id=f"m{n}"
        )
        assert d.allowed, n
    denied = await lim.check_and_increment(
        phone_ref=phone, ip_ref=ip, member_id="m6"
    )
    assert not denied.allowed
    assert denied.dimension == "phone"
    assert denied.retry_after_seconds >= 1
    # Keys never contain raw phone
    for k in fake.zsets:
        assert "138" not in k
    await lim.close()


@pytest.mark.asyncio
async def test_ip_limit_twenty_per_hour() -> None:
    fake = FakeAsyncRedis()
    lim = RedisAuthRateLimiter(
        fake,  # type: ignore[arg-type]
        env="test",
        phone_limit=1000,
        ip_limit=AUTH_IP_LIMIT,
    )
    ip = secrets.token_bytes(32)
    for n in range(20):
        d = await lim.check_and_increment(
            phone_ref=secrets.token_bytes(32),
            ip_ref=ip,
            member_id=f"ip{n}",
        )
        assert d.allowed, n
    denied = await lim.check_and_increment(
        phone_ref=secrets.token_bytes(32),
        ip_ref=ip,
        member_id="ip21",
    )
    assert not denied.allowed
    assert denied.dimension == "ip"
    await lim.close()


@pytest.mark.asyncio
async def test_ttl_set_slightly_above_window() -> None:
    fake = FakeAsyncRedis()
    lim = RedisAuthRateLimiter(fake, env="local")  # type: ignore[arg-type]
    await lim.check_and_increment(
        phone_ref=b"\x01" * 32,
        ip_ref=b"\x02" * 32,
        member_id="one",
    )
    assert AUTH_TTL_SECONDS > AUTH_WINDOW_SECONDS
    assert all(v == AUTH_TTL_SECONDS for v in fake.ttls.values())
    await lim.close()


@pytest.mark.asyncio
async def test_redis_down_fail_closed() -> None:
    fake = FakeAsyncRedis(fail=True)
    lim = RedisAuthRateLimiter(fake, env="local")  # type: ignore[arg-type]
    with pytest.raises(RateLimitBackendUnavailable):
        await lim.check_and_increment(
            phone_ref=b"\x01" * 32,
            ip_ref=b"\x02" * 32,
        )
    await lim.close()


@pytest.mark.asyncio
async def test_memory_limiter_and_metrics_hook() -> None:
    lim = MemoryAuthRateLimiter(phone_limit=2, ip_limit=10, retry_after_seconds=42)
    p, i = b"\xaa" * 32, b"\xbb" * 32
    assert (await lim.check_and_increment(phone_ref=p, ip_ref=i)).allowed
    assert (await lim.check_and_increment(phone_ref=p, ip_ref=i)).allowed
    denied = await lim.check_and_increment(phone_ref=p, ip_ref=i)
    assert not denied.allowed
    assert denied.retry_after_seconds == 42
    before = AUTH_RATE_LIMITED_TOTAL._value.get()  # type: ignore[attr-defined]
    record_auth_rate_limited()
    after = AUTH_RATE_LIMITED_TOTAL._value.get()  # type: ignore[attr-defined]
    assert after == before + 1


@pytest.mark.asyncio
async def test_winner_member_single_count_semantics() -> None:
    """Same member id still only one ZADD per call; distinct winners accumulate."""
    fake = FakeAsyncRedis()
    lim = RedisAuthRateLimiter(fake, env="t", phone_limit=5, ip_limit=20)  # type: ignore[arg-type]
    p, i = b"\x11" * 32, b"\x22" * 32
    d1 = await lim.check_and_increment(phone_ref=p, ip_ref=i, member_id="winner-a")
    d2 = await lim.check_and_increment(phone_ref=p, ip_ref=i, member_id="winner-b")
    assert d1.allowed and d2.allowed
    assert d2.phone_count == 2
    await lim.close()
