from __future__ import annotations

import asyncio
import logging
from typing import Dict, Iterable, List, Optional

from ..core.cache import AsyncTTLCache
from ..core.errors import AppError
from ..providers.base import PlatformProvider, phase_for, utcnow
from ..schemas.models import Contest, ContestsResponse, ProviderWarning
from .registry import CONTEST_PLATFORMS

log = logging.getLogger(__name__)


def _blocked(name: str) -> bool:
    n = name.lower()
    return "forecast" in n or "job" in n  # Krono's global filter


class ContestService:
    def __init__(self, providers: Dict[str, PlatformProvider], cache: AsyncTTLCache, ttl: float = 600):
        self._providers = providers
        self._cache = cache
        self._ttl = ttl

    async def upcoming(self, platforms: Optional[Iterable[str]] = None) -> ContestsResponse:
        wanted: List[str] = [p for p in (platforms or CONTEST_PLATFORMS) if p in CONTEST_PLATFORMS]

        async def fetch(pid: str) -> List[Contest]:
            return await self._cache.get_or_set(f"contests:{pid}", self._ttl, self._providers[pid].upcoming_contests)

        results = await asyncio.gather(*(fetch(p) for p in wanted), return_exceptions=True)
        contests: List[Contest] = []
        warnings: List[ProviderWarning] = []
        now = utcnow()
        for pid, res in zip(wanted, results):
            if isinstance(res, BaseException):
                log.warning("contest fetch failed for %s: %r", pid, res)
                msg = res.message if isinstance(res, AppError) else "Could not load contests"
                warnings.append(ProviderWarning(platform_id=pid, message=msg))  # type: ignore[arg-type]
                continue
            for c in res:
                phase = phase_for(c.start_time, c.end_time, now)  # cached rows go stale
                if phase == "finished" or _blocked(c.name):
                    continue
                contests.append(c.model_copy(update={"phase": phase}))
        contests.sort(key=lambda c: c.start_time)
        return ContestsResponse(contests=contests, warnings=warnings, fetched_at=now)
