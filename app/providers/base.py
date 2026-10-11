"""Provider base class and helpers shared by every platform module."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..core.errors import BadRequestError
from ..core.http import HttpClient
from ..schemas.models import Contest, ContestResult, UnifiedProfile

HANDLE_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


def validate_handle(handle: str) -> str:
    """Handles are interpolated into upstream URLs, so keep them boring."""
    handle = handle.strip()
    if not HANDLE_RE.match(handle):
        raise BadRequestError("Invalid handle: use letters, digits, '_', '-' or '.' (max 64 chars).")
    return handle


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def from_epoch(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def phase_for(start: datetime, end: datetime, now: Optional[datetime] = None) -> str:
    now = now or utcnow()
    if now > end:
        return "finished"
    if start <= now <= end:
        return "running"
    return "upcoming"


def day_key(epoch_seconds: float, tz_offset_minutes: int = 0) -> str:
    """YYYY-MM-DD of an instant as seen by a client `tz_offset_minutes` east of UTC."""
    return (from_epoch(epoch_seconds) + timedelta(minutes=tz_offset_minutes)).strftime("%Y-%m-%d")


def with_deltas(rows: List[dict]) -> List[ContestResult]:
    """rows: chronological [{event,date,place,new_rating}] -> results with rating change."""
    out: List[ContestResult] = []
    prev: Optional[int] = None
    for row in rows:
        new = row.get("new_rating")
        change = new - prev if (new is not None and prev is not None) else None
        out.append(ContestResult(event=row.get("event") or "Contest", date=row.get("date"),
                                 place=row.get("place") or 0, rating_change=change, new_rating=new))
        if new is not None:
            prev = new
    return out


class PlatformProvider:
    platform_id: str = ""

    def __init__(self, http: HttpClient):
        self.http = http

    def make_profile(self, username: str, **fields) -> UnifiedProfile:
        return UnifiedProfile(id=f"{self.platform_id}:{username}", platform_id=self.platform_id,  # type: ignore[arg-type]
                              username=username, last_updated=utcnow(), is_stale=False, **fields)

    async def profile(self, handle: str) -> UnifiedProfile:
        raise NotImplementedError

    async def contest_results(self, handle: str) -> List[ContestResult]:
        """Chronological (oldest first) contest history. Empty if unsupported."""
        return []

    async def activity(self, handle: str, tz_offset_minutes: int = 0, limit: int = 500) -> Dict[str, int]:
        return {}

    async def upcoming_contests(self) -> List[Contest]:
        return []
