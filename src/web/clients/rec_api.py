"""Internal client for the frozen recommendation API.

Requests go through the real ASGI app (httpx.ASGITransport), so Pydantic
validation and the original status codes still apply. The web layer never
computes scores and never reorders results.
"""
from __future__ import annotations

import httpx


class RecAPIError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class RecClient:
    def __init__(self, app):
        self._transport = httpx.ASGITransport(app=app)
        self._client = httpx.AsyncClient(
            transport=self._transport, base_url="http://webapp", timeout=30.0
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def recommend(self, payload: dict) -> dict:
        r = await self._client.post("/recommend", json=payload)
        if r.status_code != 200:
            raise RecAPIError(r.status_code, _detail(r))
        return r.json()

    async def article(self, nid: str) -> dict | None:
        r = await self._client.get(f"/article/{nid}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise RecAPIError(r.status_code, _detail(r))
        return r.json()

    async def similar(self, nid: str, top_k: int = 5) -> list[dict]:
        r = await self._client.get(f"/similar/{nid}", params={"top_k": top_k})
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise RecAPIError(r.status_code, _detail(r))
        return r.json().get("similar", [])


def _detail(r: httpx.Response) -> str:
    try:
        body = r.json()
        return str(body.get("detail", body))
    except Exception:
        return r.text[:200]
