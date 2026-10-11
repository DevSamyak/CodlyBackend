from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..core.errors import NotFoundError, UpstreamError
from ..schemas.models import Contest, ContestResult, Potd, UnifiedProfile
from .base import PlatformProvider, from_epoch, phase_for, utcnow, with_deltas

GRAPHQL = "https://leetcode.com/graphql"
HEADERS = {"Content-Type": "application/json", "Referer": "https://leetcode.com"}

USER_PROFILE_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile { realName userAvatar ranking }
    submitStats {
      acSubmissionNum { difficulty count }
      totalSubmissionNum { difficulty count }
    }
  }
}
"""
CONTEST_RANKING_QUERY = """
query userContestRankingInfo($username: String!) {
  userContestRanking(username: $username) { attendedContestsCount rating globalRanking topPercentage }
  userContestRankingHistory(username: $username) { attended rating ranking contest { title startTime } }
}
"""
CALENDAR_QUERY = """
query getUserCalendar($username: String!) {
  matchedUser(username: $username) { userCalendar { submissionCalendar } }
}
"""
UPCOMING_QUERY = "query { topTwoContests { title titleSlug startTime duration } }"
POTD_QUERY = """
query questionOfToday {
  activeDailyCodingChallengeQuestion { date link question { title difficulty } }
}
"""


def _count(stats: List[Dict[str, Any]], difficulty: str = "All") -> int:
    for s in stats or []:
        if s.get("difficulty") == difficulty:
            return int(s.get("count") or 0)
    return 0


def parse_profile(provider: "LeetCodeProvider", user: Dict[str, Any],
                  ranking: Optional[Dict[str, Any]]) -> UnifiedProfile:
    stats = user.get("submitStats") or {}
    rating = round(ranking["rating"]) if ranking and ranking.get("rating") else 0
    global_rank = ranking.get("globalRanking") if ranking else None
    profile = user.get("profile") or {}
    return provider.make_profile(
        user["username"], display_name=profile.get("realName") or user["username"],
        avatar=profile.get("userAvatar"), rating=rating, max_rating=rating,  # no peak rating exposed
        rank=f"#{global_rank}" if global_rank else None, global_rank=global_rank or None,
        top_percentage=ranking.get("topPercentage") if ranking else None,
        problems_solved=_count(stats.get("acSubmissionNum")),
        total_submissions=_count(stats.get("totalSubmissionNum")),
        total_contests=(ranking or {}).get("attendedContestsCount") or 0)


def parse_contest_results(history: List[Dict[str, Any]]) -> List[ContestResult]:
    rows = []
    for h in history or []:
        if not h.get("attended"):
            continue
        contest = h.get("contest") or {}
        start = contest.get("startTime")
        rows.append({"event": contest.get("title"), "date": from_epoch(start) if start else None,
                     "place": h.get("ranking") or 0,
                     "new_rating": round(h["rating"]) if h.get("rating") else None})
    return with_deltas(rows)


def parse_calendar(raw: Optional[str]) -> Dict[str, int]:
    """Keys are unix timestamps of UTC day starts."""
    if not raw:
        return {}
    days: Dict[str, int] = {}
    for ts, count in json.loads(raw).items():
        if count and count > 0:
            key = from_epoch(int(ts)).strftime("%Y-%m-%d")
            days[key] = days.get(key, 0) + int(count)
    return days


def parse_upcoming(raw: List[Dict[str, Any]]) -> List[Contest]:
    out = []
    for c in raw or []:
        start = from_epoch(c["startTime"])
        duration = int(c["duration"])
        end = from_epoch(c["startTime"] + duration)
        phase = phase_for(start, end)
        if phase == "finished":
            continue
        out.append(Contest(id=f"leetcode:{c['titleSlug']}", external_id=c["titleSlug"], platform_id="leetcode",
                           name=c["title"], start_time=start, end_time=end, duration_seconds=duration,
                           url=f"https://leetcode.com/contest/{c['titleSlug']}", is_rated=True,
                           phase=phase))  # type: ignore[arg-type]
    return out


def parse_potd(data: Dict[str, Any]) -> Optional[Potd]:
    ch = (data.get("data") or {}).get("activeDailyCodingChallengeQuestion")
    if not ch:
        return None
    return Potd(platform="leetcode", title=ch["question"]["title"], url=f"https://leetcode.com{ch['link']}",
                difficulty=ch["question"].get("difficulty") or "Unknown",
                date=ch.get("date") or utcnow().strftime("%Y-%m-%d"))


class LeetCodeProvider(PlatformProvider):
    platform_id = "leetcode"

    async def _gql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Any:
        body: Dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        data = await self.http.post_json(GRAPHQL, json=body, headers=HEADERS)
        if data.get("errors"):
            msg = data["errors"][0].get("message", "GraphQL error")
            if "does not exist" in msg.lower():
                raise NotFoundError("LeetCode user not found")
            raise UpstreamError(msg)
        return data["data"]

    async def profile(self, handle: str) -> UnifiedProfile:
        user = (await self._gql(USER_PROFILE_QUERY, {"username": handle})).get("matchedUser")
        if not user:
            raise NotFoundError("LeetCode user not found")
        ranking = None
        try:
            ranking = (await self._gql(CONTEST_RANKING_QUERY, {"username": handle})).get("userContestRanking")
        except (UpstreamError, NotFoundError):
            pass  # contest stats are optional, as in Krono
        return parse_profile(self, user, ranking)

    async def contest_results(self, handle: str) -> List[ContestResult]:
        data = await self._gql(CONTEST_RANKING_QUERY, {"username": handle})
        return parse_contest_results(data.get("userContestRankingHistory") or [])

    async def activity(self, handle: str, tz_offset_minutes: int = 0, limit: int = 500) -> Dict[str, int]:
        user = (await self._gql(CALENDAR_QUERY, {"username": handle})).get("matchedUser")
        if not user:
            raise NotFoundError("LeetCode user not found")
        return parse_calendar((user.get("userCalendar") or {}).get("submissionCalendar"))

    async def upcoming_contests(self) -> List[Contest]:
        return parse_upcoming((await self._gql(UPCOMING_QUERY)).get("topTwoContests") or [])

    async def potd(self) -> Optional[Potd]:
        return parse_potd(await self.http.post_json(GRAPHQL, json={"query": POTD_QUERY}, headers=HEADERS))
