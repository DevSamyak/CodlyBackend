import json
import unittest
from datetime import datetime, timedelta, timezone

from app.core.errors import NotFoundError, UpstreamError, UpstreamHTTPError
from app.providers import atcoder, codechef, codeforces, geeksforgeeks, topcoder
from app.providers.atcoder import AtCoderProvider
from app.providers.codechef import CodeChefProvider
from app.providers.codeforces import CodeforcesProvider
from app.providers.geeksforgeeks import GeeksForGeeksProvider
from app.providers.hackerrank import HackerRankProvider
from app.providers.leetcode import LeetCodeProvider
from app.providers.topcoder import ClistClient, TopCoderProvider

from .fakes import FakeHttp


def future(hours=24):
    return datetime.now(timezone.utc) + timedelta(hours=hours)


class CodeforcesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        sub = lambda cid, idx, verdict, t: {"id": 1, "creationTimeSeconds": t,  # noqa: E731
                                            "problem": {"contestId": cid, "index": idx, "name": "p"},
                                            "verdict": verdict}
        t = int(datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc).timestamp())
        self.subs = [sub(1, "A", "OK", t), sub(1, "A", "OK", t + 10), sub(1, "B", "WRONG_ANSWER", t),
                     sub(2, "A", "OK", t + 5)]
        self.rating = [
            {"contestName": "R1", "rank": 10, "ratingUpdateTimeSeconds": t, "oldRating": 1500, "newRating": 1560},
            {"contestName": "R2", "rank": 99, "ratingUpdateTimeSeconds": t + 99, "oldRating": 1560, "newRating": 1500}]
        self.info = [{"handle": "meet_11", "firstName": "Meet", "rating": 1500, "maxRating": 1560,
                      "rank": "specialist"}]

    def handler(self, method, url, params, body):
        if url.endswith("user.info"):
            return {"status": "OK", "result": self.info}
        if url.endswith("user.rating"):
            return {"status": "OK", "result": self.rating}
        if url.endswith("user.status"):
            return {"status": "OK", "result": self.subs}
        raise AssertionError(url)

    async def test_profile_counts_unique_accepted(self):
        p = await CodeforcesProvider(FakeHttp(self.handler)).profile("meet_11")
        self.assertEqual(p.id, "codeforces:meet_11")
        self.assertEqual((p.problems_solved, p.total_submissions, p.total_contests), (2, 4, 2))
        self.assertEqual((p.rating, p.max_rating, p.rank, p.display_name), (1500, 1560, "specialist", "Meet"))

    async def test_contest_results_have_delta(self):
        res = await CodeforcesProvider(FakeHttp(self.handler)).contest_results("meet_11")
        self.assertEqual([r.rating_change for r in res], [60, -60])
        self.assertEqual(res[0].place, 10)

    async def test_activity_counts_accepted_per_local_day(self):
        prov = CodeforcesProvider(FakeHttp(self.handler))
        self.assertEqual(await prov.activity("x", 0, 100), {"2026-10-07": 3})
        self.assertEqual(await prov.activity("x", 330, 100), {"2026-10-08": 3})

    async def test_not_found_maps_from_http_400(self):
        def h(*_):
            raise UpstreamHTTPError(400, json.dumps({"status": "FAILED", "comment": "handles: User with handle zz not found"}))

        with self.assertRaises(NotFoundError):
            await CodeforcesProvider(FakeHttp(h)).profile("zz")

    async def test_failed_status_in_body(self):
        with self.assertRaises(UpstreamError):
            await CodeforcesProvider(FakeHttp(lambda *_: {"status": "FAILED", "comment": "Call limit exceeded"})).upcoming_contests()

    def test_contest_list_filters_finished_and_past(self):
        now = int(datetime.now(timezone.utc).timestamp())
        raw = [
            {"id": 1, "name": "Old", "phase": "FINISHED", "startTimeSeconds": now - 99999, "durationSeconds": 7200},
            {"id": 2, "name": "Next", "phase": "BEFORE", "startTimeSeconds": now + 3600, "durationSeconds": 7200},
            {"id": 3, "name": "Live", "phase": "CODING", "startTimeSeconds": now - 600, "durationSeconds": 7200},
            {"id": 4, "name": "Testing", "phase": "SYSTEM_TEST", "startTimeSeconds": now - 9000, "durationSeconds": 7200},
            {"id": 5, "name": "NoDate", "phase": "BEFORE"}]
        out = codeforces.parse_contests(raw)
        self.assertEqual([c.external_id for c in out], ["2", "3"])
        self.assertEqual([c.phase for c in out], ["upcoming", "running"])
        self.assertEqual(out[0].url, "https://codeforces.com/contest/2")


class LeetCodeTests(unittest.IsolatedAsyncioTestCase):
    USER = {"username": "alice", "profile": {"realName": "Alice", "userAvatar": "http://a/png", "ranking": 1234},
            "submitStats": {"acSubmissionNum": [{"difficulty": "All", "count": 321}, {"difficulty": "Easy", "count": 100}],
                            "totalSubmissionNum": [{"difficulty": "All", "count": 700}]}}

    def handler(self, method, url, params, body):
        q = body["query"]
        if "getUserProfile" in q:
            return {"data": {"matchedUser": self.USER}}
        if "userContestRankingInfo" in q:
            return {"data": {
                "userContestRanking": {"attendedContestsCount": 3, "rating": 1789.6, "globalRanking": 4567, "topPercentage": 7.5},
                "userContestRankingHistory": [
                    {"attended": False, "rating": 1500, "ranking": 0, "contest": {"title": "Skipped", "startTime": 1700000000}},
                    {"attended": True, "rating": 1500.2, "ranking": 900, "contest": {"title": "W1", "startTime": 1700100000}},
                    {"attended": True, "rating": 1600.4, "ranking": 400, "contest": {"title": "W2", "startTime": 1700200000}}]}}
        if "getUserCalendar" in q:
            return {"data": {"matchedUser": {"userCalendar": {"submissionCalendar": json.dumps({"1700006400": 4, "1700092800": 0})}}}}
        if "topTwoContests" in q:
            return {"data": {"topTwoContests": [
                {"title": "Weekly 1", "titleSlug": "weekly-contest-1", "startTime": int(future(10).timestamp()), "duration": 5400},
                {"title": "Past", "titleSlug": "past", "startTime": 1000, "duration": 5400}]}}
        if "questionOfToday" in q:
            return {"data": {"activeDailyCodingChallengeQuestion": {
                "date": "2026-10-07", "link": "/problems/two-sum/?envType=daily",
                "question": {"title": "Two Sum", "difficulty": "Easy"}}}}
        raise AssertionError(q)

    async def test_profile(self):
        p = await LeetCodeProvider(FakeHttp(self.handler)).profile("alice")
        self.assertEqual((p.rating, p.rank, p.global_rank), (1790, "#4567", 4567))
        self.assertEqual((p.problems_solved, p.total_submissions, p.total_contests), (321, 700, 3))
        self.assertEqual(p.top_percentage, 7.5)

    async def test_missing_user_is_404(self):
        with self.assertRaises(NotFoundError):
            await LeetCodeProvider(FakeHttp(lambda *_: {"data": {"matchedUser": None}})).profile("ghost")

    async def test_unrated_user_has_zero_rating(self):
        def h(method, url, params, body):
            if "getUserProfile" in body["query"]:
                return {"data": {"matchedUser": self.USER}}
            return {"data": {"userContestRanking": None, "userContestRankingHistory": []}}

        p = await LeetCodeProvider(FakeHttp(h)).profile("alice")
        self.assertEqual((p.rating, p.rank, p.total_contests), (0, None, 0))

    async def test_history_skips_unattended_and_computes_deltas(self):
        res = await LeetCodeProvider(FakeHttp(self.handler)).contest_results("alice")
        self.assertEqual([r.event for r in res], ["W1", "W2"])
        self.assertEqual([r.rating_change for r in res], [None, 100])

    async def test_calendar_and_contests_and_potd(self):
        prov = LeetCodeProvider(FakeHttp(self.handler))
        self.assertEqual(await prov.activity("alice"), {"2023-11-15": 4})  # 1700006400 = 2023-11-15 00:00 UTC
        self.assertEqual([c.external_id for c in await prov.upcoming_contests()], ["weekly-contest-1"])
        potd = await prov.potd()
        self.assertEqual((potd.title, potd.difficulty), ("Two Sum", "Easy"))
        self.assertTrue(potd.url.startswith("https://leetcode.com/problems/two-sum"))


CC_HTML = """
<html><body>
<h1 class="h2-style">Meet Thakur</h1>
<img class='profileImage' src='https://cdn/img.png'>
<div class="rating-number">1891</div>
<div class="rating-star"><span>4&#9733;</span></div>
<div>Global Rank: <strong>1,234</strong></div>
<h3>Fully Solved (127)</h3>
<h3>Contests (57)</h3>
<script>jQuery.extend(Drupal.settings, {"date_versus_rating":{"all":[
 {"name":"Starters 1","rating":"1500","rank":"120","end_date":"2025-01-01 22:00:00"},
 {"name":"Starters 2","rating":"1700","rank":"80","end_date":"2025-01-08 22:00:00"},
 {"name":"Starters 3","rating":"1650","rank":"95","end_date":"2025-01-15 22:00:00"}
]}});</script>
</body></html>
"""


class CodeChefTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_profile(self):
        d = codechef.parse_profile_html(CC_HTML, "meetrix")
        self.assertEqual((d["rating"], d["max_rating"], d["name"]), (1650, 1700, "Meet Thakur"))
        self.assertEqual((d["avatar"], d["problems_solved"], d["total_contests"], d["rank"]),
                         ("https://cdn/img.png", 127, 57, "4 Star"))

    def test_star_fallback_from_rating(self):
        self.assertEqual([codechef.star_for(r) for r in (0, 1400, 1600, 1800, 2000, 2200, 2500)], [1, 2, 3, 4, 5, 6, 7])

    async def test_profile_and_results(self):
        prov = CodeChefProvider(FakeHttp(lambda *_: CC_HTML))
        p = await prov.profile("meetrix")
        self.assertEqual((p.rating, p.max_rating, p.rank, p.problems_solved), (1650, 1700, "4 Star", 127))
        res = await prov.contest_results("meetrix")
        self.assertEqual([r.rating_change for r in res], [None, 200, -50])
        self.assertEqual(res[0].date.utcoffset(), timedelta(hours=5, minutes=30))
        self.assertEqual(res[1].place, 80)

    async def test_404_and_empty_page_are_not_found(self):
        def h(*_):
            raise UpstreamHTTPError(404)

        with self.assertRaises(NotFoundError):
            await CodeChefProvider(FakeHttp(h)).profile("ghost")
        with self.assertRaises(NotFoundError):
            await CodeChefProvider(FakeHttp(lambda *_: "<html></html>")).profile("ghost")

    def test_contest_list(self):
        data = {"present_contests": [], "future_contests": [
            {"contest_code": "START240", "contest_name": "Starters 240",
             "contest_start_date_iso": future(5).isoformat(), "contest_end_date_iso": future(8).isoformat(),
             "contest_duration": "180"}]}
        out = codechef.parse_contests(data)
        self.assertEqual((out[0].duration_seconds, out[0].url), (180 * 60, "https://www.codechef.com/START240"))


AC_UPCOMING = """
<div id="contest-table-upcoming"><table><tbody>
<tr><td class="text-center"><a href='x'><time class='fixtime fixtime-full'>2030-01-11 21:00:00+0900</time></a></td>
<td><a href="/contests/abc387">AtCoder Beginner Contest 387</a></td>
<td class="text-center">01:40</td><td class="text-center"> ~ 1999</td></tr>
<tr><td class="text-center"><time class='fixtime fixtime-full'>2030-01-12 21:00:00+0900</time></td>
<td><a href="/contests/job1">Job Offer Contest &amp; Co</a></td>
<td class="text-center">02:00</td><td class="text-center">-</td></tr>
<tr><td class="text-center"><time class='fixtime fixtime-full'>2030-01-13 21:00:00+0900</time></td>
<td><a href="/contests/ahc99">AtCoder Heuristic &amp; Contest 99</a></td>
<td class="text-center">04:00</td><td class="text-center">-</td></tr>
</tbody></table></div>
"""


class AtCoderTests(unittest.IsolatedAsyncioTestCase):
    HISTORY = [{"NewRating": 400, "Place": 500, "ContestName": "ABC 1", "EndTime": "2024-01-13T21:40:00+09:00"},
               {"NewRating": 650, "Place": 120, "ContestName": "ABC 2", "EndTime": "2024-01-20T21:40:00+09:00"},
               {"NewRating": 600, "Place": 300, "ContestName": "ABC 3", "EndTime": "2024-01-27T21:40:00+09:00"}]

    def handler(self, method, url, params, body):
        if url.endswith("/history/json"):
            return self.HISTORY
        if "user_info" in url:
            return {"accepted_count": 321}
        if "/users/" in url:
            return "<h3><b>7 Kyu</b> user</h3>"
        raise AssertionError(url)

    async def test_profile(self):
        p = await AtCoderProvider(FakeHttp(self.handler)).profile("Chokudai")
        self.assertEqual((p.rating, p.max_rating, p.rank, p.problems_solved, p.total_contests),
                         (600, 650, "7 Kyu", 321, 3))

    async def test_rank_falls_back_to_rating_table(self):
        def h(method, url, params, body):
            if url.endswith("/history/json"):
                return self.HISTORY
            raise UpstreamError("down")

        p = await AtCoderProvider(FakeHttp(h)).profile("x")
        self.assertEqual((p.rank, p.problems_solved), ("7 Kyu", 0))

    async def test_unknown_user(self):
        def h(*_):
            raise UpstreamHTTPError(404)

        with self.assertRaises(NotFoundError):
            await AtCoderProvider(FakeHttp(h)).profile("nobody")

    async def test_contest_results(self):
        res = await AtCoderProvider(FakeHttp(self.handler)).contest_results("x")
        self.assertEqual([r.rating_change for r in res], [None, 250, -50])
        self.assertEqual(res[0].date.utcoffset(), timedelta(hours=9))

    def test_upcoming_html(self):
        abc, ahc = atcoder.parse_upcoming_html(AC_UPCOMING)  # job contest filtered out
        self.assertEqual((abc.external_id, ahc.external_id), ("abc387", "ahc99"))
        self.assertEqual((abc.duration_seconds, abc.is_rated, ahc.is_rated), (6000, True, False))
        self.assertEqual((ahc.name, ahc.duration_seconds), ("AtCoder Heuristic & Contest 99", 4 * 3600))
        self.assertEqual(abc.start_time.utcoffset(), timedelta(hours=9))

    async def test_contests_fall_back_to_kenkoooo(self):
        start = int(future(30).timestamp())

        def h(method, url, params, body):
            if url.endswith("/contests"):
                return "<html>no table</html>"
            return [{"id": "abc400", "title": "ABC 400", "start_epoch_second": start, "duration_second": 6000, "rate_change": " ~ 1999"},
                    {"id": "old", "title": "Old", "start_epoch_second": 1000, "duration_second": 10, "rate_change": "-"},
                    {"id": "f1", "title": "Rating Forecast", "start_epoch_second": start, "duration_second": 10, "rate_change": "-"}]

        out = await AtCoderProvider(FakeHttp(h)).upcoming_contests()
        self.assertEqual([c.external_id for c in out], ["abc400"])
        self.assertTrue(out[0].is_rated)


GFG_HTML = r'''<script>{"name":"Gee Ek","profile_image_url":"https:\/\/media\/x.png","coding_score":456,"total_problems_solved":99,"problems_solved":88}</script>'''


class OtherProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_gfg(self):
        p = await GeeksForGeeksProvider(FakeHttp(lambda *_: GFG_HTML)).profile("gee")
        self.assertEqual((p.rating, p.problems_solved, p.display_name), (456, 88, "Gee Ek"))
        self.assertEqual(p.avatar, "https://media/x.png")

    async def test_gfg_404(self):
        def h(*_):
            raise UpstreamHTTPError(404)

        with self.assertRaises(NotFoundError):
            await GeeksForGeeksProvider(FakeHttp(h)).profile("gee")
        with self.assertRaises(NotFoundError):
            geeksforgeeks.parse_profile_html("<h1>Page Not Found</h1>", "x")

    def test_gfg_potd_is_static_card(self):
        self.assertEqual(GeeksForGeeksProvider.potd().difficulty, "Click to Solve")

    async def test_hackerrank(self):
        def h(method, url, params, body):
            if url.endswith("/profile"):
                return {"model": {"username": "hr_user", "event_count": 4, "avatar": "http://av", "name": "HR"}}
            if url.endswith("/badges"):
                return {"models": [{"solved": 10}, {"solved": 5}, {}]}
            if url.endswith("submission_histories"):
                return {"2026-10-01": 3, "2026-10-02": 0}
            raise AssertionError(url)

        prov = HackerRankProvider(FakeHttp(h))
        p = await prov.profile("hr_user")
        self.assertEqual((p.problems_solved, p.rating, p.rank, p.total_contests), (15, 15, "Problems Solved", 4))
        self.assertEqual(await prov.activity("hr_user"), {"2026-10-01": 3})

    async def test_hackerrank_unknown(self):
        with self.assertRaises(NotFoundError):
            await HackerRankProvider(FakeHttp(lambda *_: {"model": None})).profile("x")

    async def test_topcoder_via_clist(self):
        def h(method, url, params, body):
            if url.endswith("/account/"):
                return {"objects": [{"id": 7, "handle": "tc", "name": "T C", "rating": 1620, "n_contests": 9}]}
            return {"objects": [
                {"date": "2024-02-01T10:00:00", "event": "SRM 2", "place": 5, "rating_change": 30, "new_rating": 1620},
                {"date": "2024-01-01T10:00:00", "event": "SRM 1", "place": 9, "rating_change": 1590, "new_rating": 1590},
                {"date": "2024-03-01T10:00:00", "event": "Unrated", "place": 1, "rating_change": None, "new_rating": None}]}

        http = FakeHttp(h)
        prov = TopCoderProvider(http, ClistClient(http, "u", "k"))
        p = await prov.profile("tc")
        self.assertEqual((p.rating, p.rank, p.total_contests), (1620, "Yellow", 9))
        self.assertEqual([r.event for r in await prov.contest_results("tc")], ["SRM 1", "SRM 2"])

    async def test_topcoder_without_credentials(self):
        http = FakeHttp(lambda *_: {})
        with self.assertRaises(UpstreamError):
            await TopCoderProvider(http, ClistClient(http, "", "")).profile("tc")

    def test_topcoder_ranks(self):
        self.assertEqual([topcoder.rank_title(r) for r in (0, 100, 900, 1200, 1500, 2200, 3000)],
                         ["Unrated", "Grey", "Green", "Blue", "Yellow", "Red", "Target"])


if __name__ == "__main__":
    unittest.main()
