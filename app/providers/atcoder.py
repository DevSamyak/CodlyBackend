from __future__ import annotations

import asyncio
import html as html_lib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..core.errors import NotFoundError, UpstreamError, UpstreamHTTPError
from ..schemas.models import Contest, ContestResult, UnifiedProfile
from .base import PlatformProvider, from_epoch, phase_for, with_deltas

SITE = "https://atcoder.jp"
KENKOOOO = "https://kenkoooo.com/atcoder"


def rank_title(rating: int) -> str:
    """Fallback when the profile page can't be scraped (same table as Krono)."""
    table = ((3200, "7 Dan+"), (2800, "5-6 Dan"), (2600, "4 Dan"), (2400, "3 Dan"), (2200, "2 Dan"),
             (2000, "1 Dan"), (1800, "1 Kyu"), (1600, "2 Kyu"), (1400, "3 Kyu"), (1200, "4 Kyu"),
             (1000, "5 Kyu"), (800, "6 Kyu"), (600, "7 Kyu"), (400, "8 Kyu"))
    if rating <= 0:
        return "Unrated"
    for threshold, title in table:
        if rating >= threshold:
            return title
    return "9 Kyu"


def _clean_title_ok(title: str) -> bool:
    t = title.lower()
    return "job" not in t and "forecast" not in t


def parse_rank(html: str) -> Optional[str]:
    m = re.search(r"<b>\s*(\d+\s*(?:Dan|Kyu))\s*</b>", html, re.I) or re.search(r"(\d+\s*(?:Dan|Kyu))", html, re.I)
    return m.group(1).strip() if m else None


def parse_history(history: List[Dict[str, Any]]) -> Dict[str, int]:
    if not history:
        return {"rating": 0, "max_rating": 0, "count": 0}
    return {"rating": history[-1]["NewRating"], "max_rating": max(h["NewRating"] for h in history),
            "count": len(history)}


def parse_contest_results(history: List[Dict[str, Any]]) -> List[ContestResult]:
    rows = []
    for h in history:
        try:
            date = datetime.fromisoformat(h["EndTime"])
        except (KeyError, ValueError):
            date = None
        rows.append({"event": h.get("ContestName"), "date": date, "place": h.get("Place") or 0,
                     "new_rating": h.get("NewRating")})
    return with_deltas(rows)


_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_upcoming_html(page: str) -> List[Contest]:
    """Scrape the 'Upcoming Contests' table of atcoder.jp/contests."""
    section = page.split('id="contest-table-upcoming"')
    if len(section) < 2 or "<tbody>" not in section[1]:
        return []
    tbody = section[1].split("<tbody>")[1].split("</tbody>")[0]
    out: List[Contest] = []
    for row in _ROW_RE.findall(tbody):
        cells = _CELL_RE.findall(row)
        link = re.search(r'<a href="(/contests/[^"]+)">([^<]+)</a>', row)
        when = re.search(r">(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\+0900)<", row)
        if not link or not when:
            continue
        slug = link.group(1).rsplit("/", 1)[-1]
        title = html_lib.unescape(link.group(2))
        if not _clean_title_ok(title):
            continue
        start = datetime.strptime(when.group(1), "%Y-%m-%d %H:%M:%S%z")
        duration, rated = 6000, False  # 100 min fallback, as in Krono
        if len(cells) >= 3:
            dm = re.match(r"\s*(\d+):(\d{2})\s*$", _TAG_RE.sub("", cells[2]))
            if dm:
                duration = int(dm.group(1)) * 3600 + int(dm.group(2)) * 60
        if len(cells) >= 4:
            rated = _TAG_RE.sub("", cells[3]).strip() not in ("", "-")
        end = start + timedelta(seconds=duration)
        out.append(Contest(id=f"atcoder:{slug}", external_id=slug, platform_id="atcoder", name=title,
                           start_time=start, end_time=end, duration_seconds=duration,
                           url=f"{SITE}/contests/{slug}", is_rated=rated,
                           phase=phase_for(start, end)))  # type: ignore[arg-type]
    return out


def parse_kenkoooo_contests(raw: List[Dict[str, Any]]) -> List[Contest]:
    out: List[Contest] = []
    for c in raw:
        start = from_epoch(c["start_epoch_second"])
        duration = int(c["duration_second"])
        end = from_epoch(c["start_epoch_second"] + duration)
        if phase_for(start, end) == "finished" or not _clean_title_ok(c["title"]):
            continue
        out.append(Contest(id=f"atcoder:{c['id']}", external_id=c["id"], platform_id="atcoder", name=c["title"],
                           start_time=start, end_time=end, duration_seconds=duration,
                           url=f"{SITE}/contests/{c['id']}", is_rated=c.get("rate_change", "-") != "-",
                           phase=phase_for(start, end)))  # type: ignore[arg-type]
    return out


class AtCoderProvider(PlatformProvider):
    platform_id = "atcoder"

    async def _history(self, handle: str) -> List[Dict[str, Any]]:
        try:
            data = await self.http.get_json(f"{SITE}/users/{handle}/history/json")
        except UpstreamHTTPError as exc:
            if exc.status == 404:
                raise NotFoundError("AtCoder user not found (handles are case-sensitive).") from exc
            raise UpstreamError(f"AtCoder returned HTTP {exc.status}") from exc
        return data if isinstance(data, list) else []

    async def profile(self, handle: str) -> UnifiedProfile:
        async def solved() -> int:
            data = await self.http.get_json(f"{KENKOOOO}/atcoder-api/v2/user_info", params={"user": handle})
            return int(data.get("accepted_count") or 0)

        async def rank_page() -> Optional[str]:
            return parse_rank(await self.http.get_text(f"{SITE}/users/{handle}"))

        history, accepted, rank = await asyncio.gather(
            self._history(handle), solved(), rank_page(), return_exceptions=True)
        if isinstance(history, NotFoundError):
            raise history
        if isinstance(history, BaseException):
            raise UpstreamError("Could not load AtCoder rating history")
        stats = parse_history(history)
        return self.make_profile(
            handle, display_name=handle, rating=stats["rating"], max_rating=stats["max_rating"],
            rank=rank if isinstance(rank, str) else rank_title(stats["rating"]),
            problems_solved=accepted if isinstance(accepted, int) else 0, total_contests=stats["count"])

    async def contest_results(self, handle: str) -> List[ContestResult]:
        return parse_contest_results(await self._history(handle))

    async def upcoming_contests(self) -> List[Contest]:
        try:
            contests = parse_upcoming_html(await self.http.get_text(f"{SITE}/contests"))
            if contests:
                return contests
        except (UpstreamError, UpstreamHTTPError):
            pass  # fall back to kenkoooo like Krono
        return parse_kenkoooo_contests(await self.http.get_json(f"{KENKOOOO}/resources/contests.json"))
