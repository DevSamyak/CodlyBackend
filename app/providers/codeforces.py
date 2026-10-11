from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from ..core.errors import NotFoundError, UpstreamError, UpstreamHTTPError
from ..schemas.models import Contest, ContestResult, UnifiedProfile
from .base import PlatformProvider, day_key, from_epoch, utcnow

BASE = "https://codeforces.com/api"


def parse_profile(provider: "CodeforcesProvider", user: Dict[str, Any],
                  rating_history: List[Dict[str, Any]], submissions: List[Dict[str, Any]]) -> UnifiedProfile:
    solved = {(s["problem"].get("contestId"), s["problem"].get("index"))
              for s in submissions if s.get("verdict") == "OK"}
    first = user.get("firstName")
    display = f"{first} {user.get('lastName') or ''}".strip() if first else user["handle"]
    return provider.make_profile(
        user["handle"], display_name=display, avatar=user.get("avatar"),
        rating=user.get("rating") or 0, max_rating=user.get("maxRating") or 0, rank=user.get("rank"),
        problems_solved=len(solved), total_submissions=len(submissions), total_contests=len(rating_history),
    )


def parse_contest_results(rating_history: List[Dict[str, Any]]) -> List[ContestResult]:
    return [ContestResult(event=r.get("contestName") or "Contest",
                          date=from_epoch(r["ratingUpdateTimeSeconds"]), place=r.get("rank") or 0,
                          rating_change=r["newRating"] - r["oldRating"], new_rating=r["newRating"])
            for r in rating_history]


def parse_activity(submissions: List[Dict[str, Any]], tz_offset_minutes: int) -> Dict[str, int]:
    days: Dict[str, int] = {}
    for s in submissions:
        if s.get("verdict") == "OK":
            key = day_key(s["creationTimeSeconds"], tz_offset_minutes)
            days[key] = days.get(key, 0) + 1
    return days


def parse_contests(raw: List[Dict[str, Any]]) -> List[Contest]:
    now = utcnow()
    out: List[Contest] = []
    for c in raw:
        if c.get("phase") == "FINISHED" or c.get("startTimeSeconds") is None:
            continue
        start = from_epoch(c["startTimeSeconds"])
        duration = int(c.get("durationSeconds") or 0)
        end = from_epoch(c["startTimeSeconds"] + duration)
        if end <= now:
            continue
        out.append(Contest(
            id=f"codeforces:{c['id']}", external_id=str(c["id"]), platform_id="codeforces", name=c["name"],
            start_time=start, end_time=end, duration_seconds=duration,
            url=f"https://codeforces.com/contest/{c['id']}", is_rated=True,  # same simplification as Krono
            phase="running" if c.get("phase") == "CODING" else "upcoming"))
    return out


class CodeforcesProvider(PlatformProvider):
    platform_id = "codeforces"

    async def _call(self, method: str, params: Dict[str, Any]) -> Any:
        try:
            data = await self.http.get_json(f"{BASE}/{method}", params=params)
        except UpstreamHTTPError as exc:
            comment = ""
            try:  # Codeforces answers 400 with {"status":"FAILED","comment":"..."}
                comment = json.loads(exc.body).get("comment", "")
            except (ValueError, AttributeError):
                pass
            if "not found" in comment.lower():
                raise NotFoundError(f"Codeforces user not found ({comment})") from exc
            raise UpstreamError(comment or f"Codeforces HTTP {exc.status}") from exc
        if data.get("status") != "OK":
            comment = data.get("comment", "Codeforces request failed")
            if "not found" in comment.lower():
                raise NotFoundError(comment)
            raise UpstreamError(comment)
        return data["result"]

    async def _safe(self, method: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            return await self._call(method, params)
        except (UpstreamError, NotFoundError):
            return []

    async def profile(self, handle: str) -> UnifiedProfile:
        info, rating, subs = await asyncio.gather(
            self._call("user.info", {"handles": handle}),
            self._safe("user.rating", {"handle": handle}),
            self._safe("user.status", {"handle": handle, "from": 1, "count": 5000}),
        )
        return parse_profile(self, info[0], rating, subs)

    async def contest_results(self, handle: str) -> List[ContestResult]:
        return parse_contest_results(await self._call("user.rating", {"handle": handle}))

    async def activity(self, handle: str, tz_offset_minutes: int = 0, limit: int = 500) -> Dict[str, int]:
        subs = await self._call("user.status", {"handle": handle, "from": 1, "count": limit})
        return parse_activity(subs, tz_offset_minutes)

    async def upcoming_contests(self) -> List[Contest]:
        return parse_contests(await self._call("contest.list", {"gym": "false"}))
