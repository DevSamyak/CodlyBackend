import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from app.core.cache import AsyncTTLCache
from app.core.errors import BadRequestError
from app.providers.base import day_key, phase_for, validate_handle, with_deltas


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_caches_until_ttl(self):
        now = [0.0]
        cache = AsyncTTLCache(clock=lambda: now[0])
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            return calls

        self.assertEqual(await cache.get_or_set("k", 10, factory), 1)
        self.assertEqual(await cache.get_or_set("k", 10, factory), 1)
        now[0] = 11
        self.assertEqual(await cache.get_or_set("k", 10, factory), 2)

    async def test_concurrent_callers_share_one_request(self):
        cache = AsyncTTLCache()
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.02)
            return "v"

        results = await asyncio.gather(*(cache.get_or_set("k", 10, factory) for _ in range(5)))
        self.assertEqual(results, ["v"] * 5)
        self.assertEqual(calls, 1)

    async def test_errors_are_not_cached_and_propagate_to_waiters(self):
        cache = AsyncTTLCache()
        calls = 0

        async def boom():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            raise ValueError("nope")

        res = await asyncio.gather(cache.get_or_set("k", 10, boom), cache.get_or_set("k", 10, boom),
                                   return_exceptions=True)
        self.assertTrue(all(isinstance(r, ValueError) for r in res))
        self.assertEqual(calls, 1)

        async def ok():
            return 7

        self.assertEqual(await cache.get_or_set("k", 10, ok), 7)


class HelperTests(unittest.TestCase):
    def test_validate_handle(self):
        self.assertEqual(validate_handle("  tourist "), "tourist")
        self.assertEqual(validate_handle("a.b-c_d9"), "a.b-c_d9")
        for bad in ("", "a/b", "a b", "../x", "x" * 65, "a?b=1", "a#b"):
            with self.assertRaises(BadRequestError):
                validate_handle(bad)

    def test_day_key_respects_offset(self):
        ts = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc).timestamp()
        self.assertEqual(day_key(ts, 0), "2026-10-07")
        self.assertEqual(day_key(ts, 330), "2026-10-08")  # IST has already rolled over
        self.assertEqual(day_key(ts, -300), "2026-10-07")

    def test_phase_for(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        h = timedelta(hours=1)
        self.assertEqual(phase_for(now + h, now + 2 * h, now), "upcoming")
        self.assertEqual(phase_for(now - h, now + h, now), "running")
        self.assertEqual(phase_for(now - 2 * h, now - h, now), "finished")

    def test_with_deltas(self):
        out = with_deltas([{"event": "A", "new_rating": 1000}, {"event": "B", "new_rating": 1100},
                           {"event": "C", "new_rating": 1050}])
        self.assertEqual([r.rating_change for r in out], [None, 100, -50])


if __name__ == "__main__":
    unittest.main()
