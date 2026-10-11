"""TopCoder data comes from clist.by. Credentials live in server env vars —
Krono shipped them inside the mobile bundle (EXPO_PUBLIC_*)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.errors import NotFoundError, UpstreamError
from ..core.http import HttpClient
from ..schemas.models import ContestResult, UnifiedProfile
from .base import PlatformProvider

CLIST = "https://clist.by/api/v4/json"
RESOURCE = "topcoder.com"


def rank_title(rating: int) -> str:
    for threshold, title in ((3000, "Target"), (2200, "Red"), (1500, "Yellow"), (1200, "Blue"), (900, "Green")):
        if rating >= threshold:
            return title
    return "Grey" if rating > 0 else "Unrated"


def parse_statistics(stats: List[Dict[str, Any]]) -> List[ContestResult]:
    """Clist rows -> ContestResults (chronological), rated rows only."""
    out: List[ContestResult] = []
    for s in sorted(stats, key=lambda r: r.get("date") or ""):
        if s.get("new_rating") is None:
            continue
        date: Optional[datetime] = None
        if s.get("date"):
            try:
                date = datetime.fromisoformat(s["date"])
            except ValueError:
                date = None
        change = s.get("rating_change")
        out.append(ContestResult(event=s.get("event") or "Contest", date=date,
                                 place=int(s["place"]) if str(s.get("place") or "").isdigit() else 0,
                                 rating_change=int(change) if change is not None else None,
                                 new_rating=int(s["new_rating"])))
    return out


class ClistClient:
    def __init__(self, http: HttpClient, username: str, api_key: str):
        self.http = http
        self._auth = {"Authorization": f"ApiKey {username}:{api_key}"}
        self.configured = bool(username and api_key)

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured:
            raise UpstreamError("TopCoder needs Clist credentials: set CPT_CLIST_USERNAME and CPT_CLIST_API_KEY.")
        return await self.http.get_json(f"{CLIST}/{path}/", params=params, headers=self._auth)

    async def account(self, handle: str) -> Optional[Dict[str, Any]]:
        data = await self._get("account", {"handle": handle, "resource": RESOURCE, "limit": 1})
        objects = data.get("objects") or []
        return objects[0] if objects else None

    async def statistics(self, account_id: int) -> List[Dict[str, Any]]:
        data = await self._get("statistics", {"account_id": account_id, "order_by": "date", "limit": 500})
        return data.get("objects") or []


class TopCoderProvider(PlatformProvider):
    platform_id = "topcoder"

    def __init__(self, http: HttpClient, clist: ClistClient):
        super().__init__(http)
        self.clist = clist

    async def profile(self, handle: str) -> UnifiedProfile:
        account = await self.clist.account(handle)
        if not account:
            raise NotFoundError("TopCoder user not found on Clist")
        rating = int(account.get("rating") or 0)
        return self.make_profile(
            account.get("handle") or handle, display_name=account.get("name") or account.get("handle") or handle,
            rating=rating, max_rating=rating, rank=rank_title(rating),
            total_contests=int(account.get("n_contests") or 0))

    async def contest_results(self, handle: str) -> List[ContestResult]:
        account = await self.clist.account(handle)
        if not account:
            raise NotFoundError("TopCoder user not found on Clist")
        return parse_statistics(await self.clist.statistics(account["id"]))
