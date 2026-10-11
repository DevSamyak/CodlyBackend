from __future__ import annotations

import logging

from ..core.cache import AsyncTTLCache
from ..providers.geeksforgeeks import GeeksForGeeksProvider
from ..providers.leetcode import LeetCodeProvider
from ..schemas.models import Potd, PotdResponse

log = logging.getLogger(__name__)


class PotdService:
    def __init__(self, leetcode: LeetCodeProvider, cache: AsyncTTLCache, ttl: float = 3600):
        self._lc = leetcode
        self._cache = cache
        self._ttl = ttl

    async def today(self) -> PotdResponse:
        async def lc() -> Potd | None:
            return await self._lc.potd()

        try:
            leetcode = await self._cache.get_or_set("potd:leetcode", self._ttl, lc)
        except Exception as exc:  # POTD is decoration; never fail the request
            log.warning("LeetCode POTD failed: %r", exc)
            leetcode = None
        return PotdResponse(leetcode=leetcode, gfg=GeeksForGeeksProvider.potd())
