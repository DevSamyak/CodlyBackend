"""HTTP client abstraction so providers can be unit-tested with a fake client."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class HttpClient(Protocol):
    async def get_json(self, url: str, *, params: Mapping[str, Any] | None = None,
                       headers: Mapping[str, str] | None = None) -> Any: ...

    async def get_text(self, url: str, *, params: Mapping[str, Any] | None = None,
                       headers: Mapping[str, str] | None = None) -> str: ...

    async def post_json(self, url: str, *, json: Any,
                        headers: Mapping[str, str] | None = None) -> Any: ...


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
