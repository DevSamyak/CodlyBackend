from __future__ import annotations

import asyncio
from typing import Dict, List

from ..core.cache import AsyncTTLCache
from ..core.errors import AppError, BadRequestError
from ..providers.base import PlatformProvider, validate_handle
from ..schemas.models import BatchItem, BatchResult, ContestResult, RatingPoint, UnifiedProfile


class ProfileService:
    def __init__(self, providers: Dict[str, PlatformProvider], cache: AsyncTTLCache,
                 profile_ttl: float = 300, history_ttl: float = 600):
        self._providers = providers
        self._cache = cache
        self._profile_ttl = profile_ttl
        self._history_ttl = history_ttl

    def _provider(self, platform: str) -> PlatformProvider:
        try:
            return self._providers[platform]
        except KeyError:
            raise BadRequestError(f"Unsupported platform: {platform}")

    async def profile(self, platform: str, handle: str) -> UnifiedProfile:
        handle = validate_handle(handle)
        provider = self._provider(platform)
        return await self._cache.get_or_set(f"profile:{platform}:{handle}", self._profile_ttl,
                                            lambda: provider.profile(handle))

    async def batch(self, items: List[BatchItem]) -> List[BatchResult]:
        async def one(item: BatchItem) -> BatchResult:
            try:
                profile = await self.profile(item.platform_id, item.handle)
                return BatchResult(platform_id=item.platform_id, handle=item.handle, profile=profile)
            except AppError as exc:
                return BatchResult(platform_id=item.platform_id, handle=item.handle, error=exc.message)
            except Exception:  # never let one bad item sink the whole batch
                return BatchResult(platform_id=item.platform_id, handle=item.handle, error="Unexpected error")

        return list(await asyncio.gather(*(one(i) for i in items)))

    async def _results(self, platform: str, handle: str) -> List[ContestResult]:
        handle = validate_handle(handle)
        provider = self._provider(platform)
        return await self._cache.get_or_set(f"results:{platform}:{handle}", self._history_ttl,
                                            lambda: provider.contest_results(handle))

    async def rating_history(self, platform: str, handle: str) -> List[RatingPoint]:
        return [RatingPoint(date=r.date, rating=r.new_rating, label=r.event)
                for r in await self._results(platform, handle) if r.date is not None and r.new_rating is not None]

    async def contest_history(self, platform: str, handle: str, limit: int) -> List[ContestResult]:
        """Newest first, like Krono's 'Recent activity' list."""
        return list(reversed(await self._results(platform, handle)))[:limit]

    async def activity(self, platform: str, handle: str, tz_offset_minutes: int, limit: int) -> Dict[str, int]:
        handle = validate_handle(handle)
        provider = self._provider(platform)
        return await self._cache.get_or_set(
            f"activity:{platform}:{handle}:{tz_offset_minutes}:{limit}", self._history_ttl,
            lambda: provider.activity(handle, tz_offset_minutes, limit))
