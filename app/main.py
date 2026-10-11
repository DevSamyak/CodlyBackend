from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.v1.router import api_router
from .config import get_settings
from .core.cache import AsyncTTLCache
from .core.errors import AppError
from .core.httpx_client import HttpxClient
from .deps import Services
from .services.contest_service import ContestService
from .services.potd_service import PotdService
from .services.profile_service import ProfileService
from .services.registry import build_providers


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    http = HttpxClient(timeout=s.http_timeout_seconds)
    providers = build_providers(http, s.clist_username, s.clist_api_key)
    cache: AsyncTTLCache = AsyncTTLCache()
    app.state.services = Services(
        profiles=ProfileService(providers, cache, s.profile_ttl_seconds, s.history_ttl_seconds),
        contests=ContestService(providers, cache, s.contests_ttl_seconds),
        potd=PotdService(providers["leetcode"], cache, s.potd_ttl_seconds),  # type: ignore[arg-type]
    )
    try:
        yield
    finally:
        await http.aclose()


app = FastAPI(title="CpTracker API", version="1.0.0",
              description="Aggregates Codeforces, LeetCode, CodeChef, AtCoder, GeeksforGeeks, HackerRank and "
                          "TopCoder data for the Krono Flutter app.", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


app.include_router(api_router)
