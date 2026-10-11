"""httpx-backed implementation of HttpClient."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from .errors import UpstreamError, UpstreamHTTPError
from .http import BROWSER_UA


class HttpxClient:
    def __init__(self, timeout: float = 20.0, user_agent: str = BROWSER_UA):
        self._client = httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent}
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            resp = await self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise UpstreamError(f"Timed out contacting {httpx.URL(url).host}") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Could not reach {httpx.URL(url).host}") from exc
        if resp.status_code >= 400:
            raise UpstreamHTTPError(resp.status_code, resp.text[:2000])
        return resp

    @staticmethod
    def _json(resp: httpx.Response, url: str) -> Any:
        try:
            return resp.json()
        except ValueError as exc:
            raise UpstreamError(f"Invalid JSON from {httpx.URL(url).host}") from exc

    async def get_json(self, url: str, *, params: Mapping[str, Any] | None = None,
                       headers: Mapping[str, str] | None = None) -> Any:
        return self._json(await self._request("GET", url, params=params, headers=headers), url)

    async def get_text(self, url: str, *, params: Mapping[str, Any] | None = None,
                       headers: Mapping[str, str] | None = None) -> str:
        return (await self._request("GET", url, params=params, headers=headers)).text

    async def post_json(self, url: str, *, json: Any,
                        headers: Mapping[str, str] | None = None) -> Any:
        return self._json(await self._request("POST", url, json=json, headers=headers), url)
