"""A scriptable HttpClient for tests: no network, no httpx."""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

Handler = Callable[[str, str, Optional[dict], Any], Any]


class FakeHttp:
    """handler(method, url, params, json) returns the payload or raises."""

    def __init__(self, handler: Handler):
        self.handler = handler
        self.calls: List[Tuple[str, str]] = []

    async def get_json(self, url, *, params=None, headers=None):
        self.calls.append(("GET", url))
        return self.handler("GET", url, params, None)

    async def get_text(self, url, *, params=None, headers=None):
        self.calls.append(("GET", url))
        return self.handler("GET", url, params, None)

    async def post_json(self, url, *, json, headers=None):
        self.calls.append(("POST", url))
        return self.handler("POST", url, None, json)
