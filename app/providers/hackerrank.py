from __future__ import annotations

from typing import Any, Dict

from ..core.errors import NotFoundError, UpstreamError, UpstreamHTTPError
from ..schemas.models import UnifiedProfile
from .base import PlatformProvider

BASE = "https://www.hackerrank.com/rest"


def parse_badges_total(badges: Dict[str, Any]) -> int:
    return sum(int(b.get("solved") or 0) for b in (badges or {}).get("models") or [])


def parse_submission_history(raw: Any) -> Dict[str, int]:
    """HackerRank returns {"YYYY-MM-DD": count}."""
    if not isinstance(raw, dict):
        return {}
    return {k: int(v) for k, v in raw.items() if isinstance(v, (int, float)) and v > 0}


class HackerRankProvider(PlatformProvider):
    platform_id = "hackerrank"

    async def profile(self, handle: str) -> UnifiedProfile:
        try:
            data = await self.http.get_json(f"{BASE}/contests/master/hackers/{handle}/profile")
        except UpstreamHTTPError as exc:
            if exc.status == 404:
                raise NotFoundError("HackerRank user not found") from exc
            raise UpstreamError(f"HackerRank returned HTTP {exc.status}") from exc
        model = data.get("model") if isinstance(data, dict) else None
        if not model:
            raise NotFoundError("HackerRank user not found")
        solved = 0
        try:
            solved = parse_badges_total(await self.http.get_json(f"{BASE}/hackers/{handle}/badges"))
        except (UpstreamError, UpstreamHTTPError):
            pass  # optional, like Krono
        username = model.get("username") or handle
        return self.make_profile(
            username, display_name=model.get("name") or username, avatar=model.get("avatar"),
            rating=solved, max_rating=solved,  # Krono shows "problems solved" as the hero number
            rank="Problems Solved", problems_solved=solved, total_submissions=solved,
            total_contests=int(model.get("event_count") or 0))

    async def activity(self, handle: str, tz_offset_minutes: int = 0, limit: int = 500) -> Dict[str, int]:
        try:
            raw = await self.http.get_json(f"{BASE}/hackers/{handle}/submission_histories")
        except UpstreamHTTPError:
            return {}
        return parse_submission_history(raw)
