"""Tiny async TTL cache with in-flight de-duplication.

Concurrent callers asking for the same key share one upstream request.
Failures are never cached.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Dict, Generic, Tuple, TypeVar

T = TypeVar("T")


class AsyncTTLCache(Generic[T]):
    def __init__(self, clock: Callable[[], float] = time.monotonic, max_entries: int = 2048):
        self._clock = clock
        self._max = max_entries
        self._data: Dict[str, Tuple[float, T]] = {}
        self._inflight: Dict[str, "asyncio.Future[T]"] = {}

    def _purge(self) -> None:
        now = self._clock()
        for key in [k for k, (exp, _) in self._data.items() if exp <= now]:
            del self._data[key]
        if len(self._data) >= self._max:
            for key, _ in sorted(self._data.items(), key=lambda kv: kv[1][0])[: max(1, self._max // 10)]:
                del self._data[key]

    async def get_or_set(self, key: str, ttl: float, factory: Callable[[], Awaitable[T]]) -> T:
        hit = self._data.get(key)
        if hit is not None and hit[0] > self._clock():
            return hit[1]

        pending = self._inflight.get(key)
        if pending is not None:
            return await asyncio.shield(pending)

        future: "asyncio.Future[T]" = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            value = await factory()
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved: no "never retrieved" warning if nobody waited
            raise
        else:
            if len(self._data) >= self._max:
                self._purge()
            self._data[key] = (self._clock() + ttl, value)
            future.set_result(value)
            return value
        finally:
            self._inflight.pop(key, None)

    def clear(self) -> None:
        self._data.clear()
