from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ..core.errors import NotFoundError, UpstreamError, UpstreamHTTPError
from ..schemas.models import Potd, UnifiedProfile
from .base import PlatformProvider, utcnow


def parse_profile_html(html: str, handle: str) -> Dict[str, Any]:
    """Regex scraper ported from Krono's geeksforgeeks.ts."""
    if not html or "Page Not Found" in html or "404 Error" in html:
        raise NotFoundError("GeeksforGeeks user not found")

    def first_int(*patterns: str) -> int:
        for p in patterns:
            m = re.search(p, html, re.I | re.S)
            if m and m.group(1):
                return int(m.group(1))
        return 0

    solved = first_int(
        # anchored so "total_problems_solved" doesn't satisfy the exact-key pattern
        r'(?<![A-Za-z_])problems_solved(?:\\"|")?\s*:\s*(\d+)',
        r"Total Problem Solved.*?<span[^>]*>(\d+)</span>",
        r'total_problems?_solved(?:\\"|")?\s*:\s*(\d+)')
    score = first_int(
        r'coding_score(?:\\"|")?\s*:\s*(\d+)',
        r'overall_coding_score(?:\\"|")?\s*:\s*(\d+)',
        r"Overall Coding Score.*?<span[^>]*>(\d+)</span>")
    avatar: Optional[str] = None
    m = re.search(r'profile_image_url(?:\\"|")?\s*:\s*(?:\\"|")((?:[^\\"]|\\/)+)(?:\\"|")', html, re.I)
    if m:
        avatar = m.group(1).replace("\\/", "/")
    name = handle
    m = re.search(r'name(?:\\"|")?\s*:\s*(?:\\"|")([^\\"]+)(?:\\"|")', html, re.I)
    if m:
        name = m.group(1)
    return {"score": score, "solved": solved, "avatar": avatar, "name": name}


class GeeksForGeeksProvider(PlatformProvider):
    platform_id = "geeksforgeeks"

    async def profile(self, handle: str) -> UnifiedProfile:
        try:
            html = await self.http.get_text(f"https://www.geeksforgeeks.org/user/{handle}/")
        except UpstreamHTTPError as exc:
            if exc.status == 404:
                raise NotFoundError("GeeksforGeeks user not found") from exc
            raise UpstreamError(f"GeeksforGeeks returned HTTP {exc.status}") from exc
        d = parse_profile_html(html, handle)
        return self.make_profile(handle, display_name=d["name"], avatar=d["avatar"], rating=d["score"],
                                 max_rating=d["score"], problems_solved=d["solved"], total_submissions=d["solved"])

    @staticmethod
    def potd() -> Potd:
        # No public POTD API: static card linking to the page (as Krono).
        return Potd(platform="geeksforgeeks", title="Solve Today's Problem",
                    url="https://practice.geeksforgeeks.org/problem-of-the-day",
                    difficulty="Click to Solve", date=utcnow().strftime("%Y-%m-%d"))
