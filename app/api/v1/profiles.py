from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...deps import Services, get_services
from ...schemas.models import (ActivityResponse, BatchRequest, BatchResponse, ContestHistoryResponse, PlatformId,
                               RatingHistoryResponse, UnifiedProfile)

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("/batch", response_model=BatchResponse, summary="Refresh many profiles at once")
async def batch_profiles(body: BatchRequest, svc: Services = Depends(get_services)):
    return BatchResponse(results=await svc.profiles.batch(body.items))


@router.get("/{platform}/{handle}", response_model=UnifiedProfile)
async def get_profile(platform: PlatformId, handle: str, svc: Services = Depends(get_services)):
    return await svc.profiles.profile(platform, handle)


@router.get("/{platform}/{handle}/rating-history", response_model=RatingHistoryResponse)
async def rating_history(platform: PlatformId, handle: str, svc: Services = Depends(get_services)):
    points = await svc.profiles.rating_history(platform, handle)
    return RatingHistoryResponse(platform_id=platform, handle=handle, points=points)


@router.get("/{platform}/{handle}/contest-history", response_model=ContestHistoryResponse)
async def contest_history(platform: PlatformId, handle: str, limit: int = Query(20, ge=1, le=100),
                          svc: Services = Depends(get_services)):
    entries = await svc.profiles.contest_history(platform, handle, limit)
    return ContestHistoryResponse(platform_id=platform, handle=handle, entries=entries)


@router.get("/{platform}/{handle}/activity", response_model=ActivityResponse)
async def activity(platform: PlatformId, handle: str,
                   tz_offset_minutes: int = Query(0, alias="tzOffsetMinutes", ge=-840, le=840),
                   limit: int = Query(500, ge=1, le=10000), svc: Services = Depends(get_services)):
    days = await svc.profiles.activity(platform, handle, tz_offset_minutes, limit)
    return ActivityResponse(platform_id=platform, handle=handle, days=days, total=sum(days.values()))
