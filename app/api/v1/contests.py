from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ...deps import Services, get_services
from ...schemas.models import ContestsResponse, PotdResponse

router = APIRouter(tags=["contests"])


@router.get("/contests", response_model=ContestsResponse, summary="Upcoming and running contests")
async def list_contests(
    platforms: Optional[List[str]] = Query(None, description="Repeat or comma-separate: ?platforms=codeforces,atcoder"),
    svc: Services = Depends(get_services),
):
    flat: Optional[List[str]] = None
    if platforms:
        flat = [p.strip() for item in platforms for p in item.split(",") if p.strip()]
    return await svc.contests.upcoming(flat)


@router.get("/potd", response_model=PotdResponse, summary="Problem of the day")
async def potd(svc: Services = Depends(get_services)):
    return await svc.potd.today()
