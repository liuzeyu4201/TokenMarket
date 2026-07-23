"""RedisRateLimiter unit tests with a fake async Redis client (T072 coverage)."""

from __future__ import annotations

from typing import Any

import pytest

from app.rate_limit import RateLimitBackendUnavailable, RedisRateLimiter


class FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def pipeline(self) -> "FakePipeline":
        if self.fail:
            raise ConnectionError("redis down")
        return FakePipeline(self)

    async def aclose(self) -> None:
        return None


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, Any]] = []

    def incr(self, key: str) -> None:
        self._ops.append(("incr", key))

    def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        self._ops.append(("expire", (key, seconds, nx)))

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for op, arg in self._ops:
            if op == "incr":
                key = arg
                self._redis.store[key] = self._redis.store.get(key, 0) + 1
                results.append(self._redis.store[key])
            elif op == "expire":
                key, seconds, _nx = arg
                if key not in self._redis.ttls:
                    self._redis.ttls[key] = seconds
                results.append(True)
        return results


@pytest.mark.asyncio
async def test_redis_rate_limiter_allows_then_blocks() -> None:
    fake = FakeRedis()
    lim = RedisRateLimiter(fake, ip_limit=2, phone_limit=5)  # type: ignore[arg-type]
    assert (await lim.check_and_increment(ip="1.1.1.1", phone_normalized=None)).allowed
    assert (await lim.check_and_increment(ip="1.1.1.1", phone_normalized=None)).allowed
    d = await lim.check_and_increment(ip="1.1.1.1", phone_normalized=None)
    assert not d.allowed
    await lim.close()


@pytest.mark.asyncio
async def test_redis_rate_limiter_fail_closed() -> None:
    fake = FakeRedis(fail=True)
    lim = RedisRateLimiter(fake, ip_limit=10, phone_limit=10)  # type: ignore[arg-type]
    with pytest.raises(RateLimitBackendUnavailable):
        await lim.check_and_increment(ip="1.1.1.1", phone_normalized="13800138000")
