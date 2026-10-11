"""API schemas. JSON uses camelCase to mirror Krono's TypeScript types."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

PlatformId = Literal["codeforces", "leetcode", "codechef", "atcoder", "geeksforgeeks", "topcoder", "hackerrank"]
ContestPhase = Literal["upcoming", "running", "finished"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Badge(CamelModel):
    id: str
    name: str
    icon: Optional[str] = None
    description: Optional[str] = None


class UnifiedProfile(CamelModel):
    id: str  # "codeforces:tourist"
    platform_id: PlatformId
    username: str
    display_name: Optional[str] = None
    avatar: Optional[str] = None
    rating: int = 0
    max_rating: int = 0
    rank: Optional[str] = None
    global_rank: Optional[int] = None
    top_percentage: Optional[float] = None
    problems_solved: int = 0
    total_submissions: int = 0
    total_contests: int = 0
    badges: List[Badge] = Field(default_factory=list)
    last_updated: datetime
    is_stale: bool = False


class Contest(CamelModel):
    id: str
    external_id: str
    platform_id: PlatformId
    name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    url: str
    is_rated: bool = True
    phase: ContestPhase = "upcoming"


class ProviderWarning(CamelModel):
    platform_id: PlatformId
    message: str


class ContestsResponse(CamelModel):
    contests: List[Contest]
    warnings: List[ProviderWarning] = Field(default_factory=list)
    fetched_at: datetime


class ContestResult(CamelModel):
    """One contest in a user's history."""

    event: str
    date: Optional[datetime] = None
    place: int = 0
    rating_change: Optional[int] = None
    new_rating: Optional[int] = None


class RatingPoint(CamelModel):
    date: datetime
    rating: int
    label: Optional[str] = None


class RatingHistoryResponse(CamelModel):
    platform_id: PlatformId
    handle: str
    points: List[RatingPoint]


class ContestHistoryResponse(CamelModel):
    platform_id: PlatformId
    handle: str
    entries: List[ContestResult]


class ActivityResponse(CamelModel):
    platform_id: PlatformId
    handle: str
    days: Dict[str, int]  # "YYYY-MM-DD" -> solved/accepted count
    total: int


class Potd(CamelModel):
    platform: Literal["leetcode", "geeksforgeeks"]
    title: str
    url: str
    difficulty: str  # Easy | Medium | Hard | Unknown | Click to Solve
    date: str


class PotdResponse(CamelModel):
    leetcode: Optional[Potd] = None
    gfg: Optional[Potd] = None


class BatchItem(CamelModel):
    platform_id: PlatformId
    handle: str = Field(min_length=1, max_length=64)


class BatchRequest(CamelModel):
    items: List[BatchItem] = Field(min_length=1, max_length=25)


class BatchResult(CamelModel):
    platform_id: PlatformId
    handle: str
    profile: Optional[UnifiedProfile] = None
    error: Optional[str] = None


class BatchResponse(CamelModel):
    results: List[BatchResult]
