"""通用按 key 限速器。

防止对同一目标（域名 / 接口 / 账号）过于频繁地发起请求：
- 随机抖动让请求模式更自然
- 全局单例便于各业务共享同一限速节奏

用法：
    limiter = get_rate_limiter(min_interval=1.0, max_interval=3.0)
    await limiter.wait("api.example.com")
    # ... 发起请求 ...
"""

from __future__ import annotations

import asyncio
import random
import time

from service_mcp.utils.log import get_logger


logger = get_logger(__name__)


class KeyRateLimiter:
    """按 key 限速器，带随机抖动。

    Args:
        min_interval: 同一 key 两次请求之间的最小间隔（秒）。
        max_interval: 最大间隔（秒），实际等待间隔在 [min, max] 内随机。
    """

    def __init__(self, min_interval: float = 2.0, max_interval: float = 5.0):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._last_request: dict[str, float] = {}

    async def wait(self, key: str) -> None:
        """如需要，在访问该 key 前等待。

        Args:
            key: 限速维度（域名 / 接口 / 账号等）。
        """
        if key in self._last_request:
            elapsed = time.time() - self._last_request[key]
            target_interval = random.uniform(self.min_interval, self.max_interval)

            if elapsed < target_interval:
                wait_time = target_interval - elapsed
                logger.debug(f"Rate limiting: waiting {wait_time:.1f}s before request to {key}")
                await asyncio.sleep(wait_time)

        self._last_request[key] = time.time()

    def reset(self, key: str | None = None) -> None:
        """重置单个 key 或全部 key 的限速状态。"""
        if key:
            self._last_request.pop(key, None)
        else:
            self._last_request.clear()


# 全局单例，供各业务共享
_global_limiter: KeyRateLimiter | None = None


def get_rate_limiter(min_interval: float = 2.0, max_interval: float = 5.0) -> KeyRateLimiter:
    """获取或创建全局限速器单例。"""
    global _global_limiter
    limiter = _global_limiter
    if limiter is None:
        limiter = KeyRateLimiter(min_interval=min_interval, max_interval=max_interval)
        _global_limiter = limiter
    return limiter
