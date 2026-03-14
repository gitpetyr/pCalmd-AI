"""Asyncio semaphore + sliding-window rate control for API requests."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Controls concurrent and per-minute API request rates.

    Uses :class:`asyncio.Semaphore` for concurrency and a sliding window
    for per-minute rate limiting.  Supports use as an async context manager::

        async with rate_limiter:
            await provider.complete(...)
    """

    def __init__(
        self, max_concurrent: int = 3, requests_per_minute: int = 50
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rpm = requests_per_minute
        self._timestamps: list[float] = []  # sliding window of request timestamps

    async def acquire(self) -> None:
        """Wait until both concurrency and rate limits allow a request."""
        await self._semaphore.acquire()
        await self._wait_for_rate_limit()
        self._timestamps.append(time.monotonic())

    def release(self) -> None:
        """Release the concurrency semaphore."""
        self._semaphore.release()

    async def __aenter__(self) -> RateLimiter:
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.release()

    async def _wait_for_rate_limit(self) -> None:
        """Wait until the sliding window allows another request."""
        window = 60.0  # 1 minute
        while True:
            now = time.monotonic()
            # Remove timestamps older than the window.
            self._timestamps = [t for t in self._timestamps if now - t < window]
            if len(self._timestamps) < self._rpm:
                return
            # Wait until the oldest timestamp expires from the window.
            sleep_time = window - (now - self._timestamps[0])
            await asyncio.sleep(max(0.1, sleep_time))
