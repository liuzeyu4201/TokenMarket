"""In-memory rate limiter behavior (FR-019 / FR-020a)."""

from __future__ import annotations

import pytest

from app.rate_limit import MemoryRateLimiter, RateLimitBackendUnavailable


@pytest.mark.asyncio
async def test_ip_limit() -> None:
    lim = MemoryRateLimiter(ip_limit=2, phone_limit=100)
    assert (await lim.check_and_increment(ip="1.1.1.1", phone_normalized=None)).allowed
    assert (await lim.check_and_increment(ip="1.1.1.1", phone_normalized=None)).allowed
    d = await lim.check_and_increment(ip="1.1.1.1", phone_normalized=None)
    assert not d.allowed


@pytest.mark.asyncio
async def test_phone_only_when_normalized() -> None:
    lim = MemoryRateLimiter(ip_limit=100, phone_limit=1)
    assert (await lim.check_and_increment(ip="2.2.2.2", phone_normalized=None)).allowed
    assert (
        await lim.check_and_increment(ip="2.2.2.2", phone_normalized="13800138000")
    ).allowed
    d = await lim.check_and_increment(ip="2.2.2.2", phone_normalized="13800138000")
    assert not d.allowed


@pytest.mark.asyncio
async def test_fail_closed() -> None:
    lim = MemoryRateLimiter(fail=True)
    with pytest.raises(RateLimitBackendUnavailable):
        await lim.check_and_increment(ip="1.1.1.1", phone_normalized=None)
