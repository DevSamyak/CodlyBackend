from fastapi import APIRouter

from . import contests, profiles

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(profiles.router)
api_router.include_router(contests.router)
