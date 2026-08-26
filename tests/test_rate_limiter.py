"""测试通用限速器（utils/rate_limiter.py）"""

import asyncio
import time

from service_mcp.utils.rate_limiter import KeyRateLimiter, get_rate_limiter


async def test_wait_respects_min_interval():
    limiter = KeyRateLimiter(min_interval=0.05, max_interval=0.05)

    # 第一次调用不等待
    start = time.monotonic()
    await limiter.wait("key-a")
    first_elapsed = time.monotonic() - start
    assert first_elapsed < 0.03

    # 第二次调用需要等待约 min_interval
    start = time.monotonic()
    await limiter.wait("key-a")
    second_elapsed = time.monotonic() - start
    assert second_elapsed >= 0.03


async def test_wait_is_per_key():
    limiter = KeyRateLimiter(min_interval=0.2, max_interval=0.2)
    await limiter.wait("key-a")
    # 不同 key 不受影响
    start = time.monotonic()
    await limiter.wait("key-b")
    assert time.monotonic() - start < 0.1


async def test_reset():
    limiter = KeyRateLimiter(min_interval=0.2, max_interval=0.2)
    await limiter.wait("key-a")
    limiter.reset("key-a")
    start = time.monotonic()
    await limiter.wait("key-a")
    assert time.monotonic() - start < 0.1

    await limiter.wait("key-a")
    limiter.reset()
    start = time.monotonic()
    await limiter.wait("key-a")
    assert time.monotonic() - start < 0.1


def test_get_rate_limiter_singleton():
    a = get_rate_limiter()
    b = get_rate_limiter()
    assert a is b
    assert isinstance(a, KeyRateLimiter)


async def test_parallel_waits_are_isolated():
    limiter = KeyRateLimiter(min_interval=0.05, max_interval=0.05)
    await asyncio.gather(limiter.wait("a"), limiter.wait("b"), limiter.wait("c"))
    assert len(limiter._last_request) == 3  # noqa: SLF001
