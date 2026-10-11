from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..core.errors import NotFoundError, UpstreamError, UpstreamHTTPError
from ..schemas.models import Contest, ContestResult, UnifiedProfile
from .base import PlatformProvider, phase_for, with_deltas

BASE = "https://www.codechef.com"
IST = timezone(timedelta(hours=5, minutes=30))  # CodeChef shows India time


def star_for(rating: int) -> int:
    for threshold, star in ((2500, 7), (2200, 6), (2000, 5), (1800, 4), (1600, 3), (1400, 2)):
        if rating >= threshold:
            return star
    return 1


def parse_profile_html(html: str, handle: str) -> Dict[str, Any]:
    """Port of Krono's regex scraper."""
    rating = max_rating = 0
    history: List[Dict[str, Any]] = []

    settings = re.search(r"jQuery\.extend\(Drupal\.settings,\s*(\{.*?\})\);", html, re.S)
    if settings:
        try:
            data = json.loads(settings.group(1))
            history = (data.get("date_versus_rating") or {}).get("all") or []
            if history:
                ratings = [int(x["rating"]) for x in history]
                rating, max_rating = ratings[-1], max(ratings)
        except (ValueError, KeyError, TypeError):
            history = []

    if not rating:
        m = re.search(r'<div class="rating-number">(\d+)</div>', html)
        rating = int(m.group(1)) if m else 0

    star: Optional[str] = None
    for pattern in (r">\s*(\d+)&#9733;", r">\s*(\d+)\s*★", r"(\d+)\s*Star"):
        m = re.search(pattern, html, re.I)
        if m:
            star = m.group(1)
            break

    gr = re.search(r"Global Rank:.*?<strong[^>]*>\s*(\d+)", html, re.I | re.S)

    solved = 0
    for pattern in (r"Fully Solved\s*\((\d+)\)", r"Problems Solved\s*:\s*(\d+)", r">\s*Solved\s*:\s*(\d+)"):
        m = re.search(pattern, html, re.I)
        if m:
            solved = int(m.group(1))
            break

    avatar = (re.search(r"""<img[^>]*class=['"]profileImage['"][^>]*src=['"]([^'"]+)['"]""", html)
              or re.search(r'<img src="([^"]+)"[^>]*class="user-img', html))
    name = (re.search(r"<h1[^>]*>\s*([^<]+?)\s*</h1>", html)
            or re.search(r"<h1[^>]*>(?:<span[^>]*>)?([^<]+)(?:</span>)?</h1>", html))
    contests = (re.search(r"Contests \((.*?)\)", html, re.I)
                or re.search(r"Contests[a-zA-Z\s<>]*:\s*(?:<strong>|<b>)?\s*(\d+)", html, re.I))
    total_contests = len(history)
    if contests and contests.group(1).strip().isdigit():
        total_contests = int(contests.group(1))

    return {
        "handle": handle, "rating": rating, "max_rating": max_rating or rating,
        "rank": f"{star or star_for(rating)} Star",
        "global_rank": int(gr.group(1)) if gr else None,
        "problems_solved": solved, "total_contests": total_contests, "rating_history": history,
        "avatar": avatar.group(1) if avatar else None,
        "name": name.group(1).strip() if name else handle,
        "has_signal": bool(settings or rating or name or solved),
    }


def parse_contest_results(history: List[Dict[str, Any]]) -> List[ContestResult]:
    rows = []
    for h in history:
        end = None
        if h.get("end_date"):
            try:
                end = datetime.fromisoformat(h["end_date"].replace(" ", "T")).replace(tzinfo=IST)
            except ValueError:
                end = None
        try:
            place = int(h.get("rank") or 0)
        except ValueError:
            place = 0
        rows.append({"event": h.get("name"), "date": end, "place": place, "new_rating": int(h["rating"])})
    return with_deltas(rows)


def parse_contests(data: Dict[str, Any]) -> List[Contest]:
    out: List[Contest] = []
    for c in (data.get("present_contests") or []) + (data.get("future_contests") or []):
        start = datetime.fromisoformat(c["contest_start_date_iso"])
        end = datetime.fromisoformat(c["contest_end_date_iso"])
        phase = phase_for(start, end)
        if phase == "finished":
            continue
        out.append(Contest(id=f"codechef:{c['contest_code']}", external_id=c["contest_code"], platform_id="codechef",
                           name=c["contest_name"], start_time=start, end_time=end,
                           duration_seconds=int(c["contest_duration"]) * 60,  # minutes -> seconds
                           url=f"{BASE}/{c['contest_code']}", is_rated=True,
                           phase=phase))  # type: ignore[arg-type]
    return out


class CodeChefProvider(PlatformProvider):
    platform_id = "codechef"

    async def _page(self, handle: str) -> Dict[str, Any]:
        try:
            html = await self.http.get_text(f"{BASE}/users/{handle}", headers={"Accept": "text/html"})
        except UpstreamHTTPError as exc:
            if exc.status == 404:
                raise NotFoundError("CodeChef user not found") from exc
            raise UpstreamError(f"CodeChef returned HTTP {exc.status}") from exc
        return parse_profile_html(html, handle)

    async def profile(self, handle: str) -> UnifiedProfile:
        d = await self._page(handle)
        if not d["has_signal"]:
            raise NotFoundError("CodeChef user not found or profile hidden")
        return self.make_profile(
            d["handle"], display_name=d["name"], avatar=d["avatar"], rating=d["rating"],
            max_rating=d["max_rating"], rank=d["rank"], global_rank=d["global_rank"],
            problems_solved=d["problems_solved"], total_submissions=d["problems_solved"],  # fallback like Krono
            total_contests=d["total_contests"])

    async def contest_results(self, handle: str) -> List[ContestResult]:
        return parse_contest_results((await self._page(handle))["rating_history"])

    async def upcoming_contests(self) -> List[Contest]:
        data = await self.http.get_json(
            f"{BASE}/api/list/contests/all",
            params={"sort_by": "START", "sorting_order": "asc", "offset": 0, "mode": "all"},
            headers={"Accept": "application/json"})
        return parse_contests(data)
