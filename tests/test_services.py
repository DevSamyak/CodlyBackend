import unittest
from datetime import datetime, timedelta, timezone

from app.core.cache import AsyncTTLCache
from app.core.errors import BadRequestError, NotFoundError, UpstreamError
from app.providers.base import PlatformProvider
from app.schemas.models import BatchItem, Contest, UnifiedProfile
from app.services.contest_service import ContestService
from app.services.profile_service import ProfileService


def contest(pid, cid, name, start_h, dur_h=2):
    s = datetime.now(timezone.utc) + timedelta(hours=start_h)
    return Contest(id=f"{pid}:{cid}", external_id=cid, platform_id=pid, name=name, start_time=s,
                   end_time=s + timedelta(hours=dur_h), duration_seconds=dur_h * 3600, url="http://x")


class StubProvider(PlatformProvider):
    platform_id = "codeforces"

    def __init__(self, contests=None, fail=None):
        super().__init__(None)  # type: ignore[arg-type]
        self.contests, self.fail, self.profile_calls = contests or [], fail, 0

    async def profile(self, handle):
        self.profile_calls += 1
        if handle == "ghost":
            raise NotFoundError("no such user")
        return self.make_profile(handle, rating=100)

    async def upcoming_contests(self):
        if self.fail:
            raise self.fail
        return self.contests


class StubOther(StubProvider):
    platform_id = "atcoder"


class ProfileServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_cached_and_validated(self):
        prov = StubProvider()
        svc = ProfileService({"codeforces": prov}, AsyncTTLCache())
        a = await svc.profile("codeforces", "tourist")
        self.assertIs(a, await svc.profile("codeforces", "tourist"))
        self.assertEqual(prov.profile_calls, 1)
        with self.assertRaises(BadRequestError):
            await svc.profile("codeforces", "../etc/passwd")

    async def test_batch_reports_per_item_errors(self):
        svc = ProfileService({"codeforces": StubProvider()}, AsyncTTLCache())
        out = await svc.batch([BatchItem(platform_id="codeforces", handle="ok"),
                               BatchItem(platform_id="codeforces", handle="ghost"),
                               BatchItem(platform_id="codeforces", handle="bad/handle"),
                               BatchItem(platform_id="leetcode", handle="nope")])
        self.assertIsNotNone(out[0].profile)
        self.assertEqual(out[1].error, "no such user")
        self.assertIn("Invalid handle", out[2].error)
        self.assertIn("Unsupported", out[3].error)


class ContestServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_merges_sorts_filters_and_reports_failures(self):
        cf = StubProvider([contest("codeforces", "2", "Later", 30), contest("codeforces", "1", "Soon", 2),
                           contest("codeforces", "3", "Live", -1), contest("codeforces", "4", "Over", -5),
                           contest("codeforces", "5", "Rating Forecast", 3)])
        ac = StubOther(fail=UpstreamError("AtCoder down"))
        res = await ContestService({"codeforces": cf, "atcoder": ac}, AsyncTTLCache()).upcoming(
            ["codeforces", "atcoder", "geeksforgeeks"])
        self.assertEqual([c.name for c in res.contests], ["Live", "Soon", "Later"])
        self.assertEqual([c.phase for c in res.contests], ["running", "upcoming", "upcoming"])
        self.assertEqual([(w.platform_id, w.message) for w in res.warnings], [("atcoder", "AtCoder down")])


class SchemaTests(unittest.TestCase):
    def test_serializes_camel_case(self):
        p = UnifiedProfile(id="a:b", platform_id="atcoder", username="b", last_updated=datetime.now(timezone.utc))
        d = p.model_dump(by_alias=True, mode="json")
        for key in ("platformId", "maxRating", "problemsSolved", "totalContests", "lastUpdated", "isStale"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
