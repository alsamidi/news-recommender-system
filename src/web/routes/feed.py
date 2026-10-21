"""Feed routing: persona (warm) -> history (cold) -> popular.

Implements the approved decision tree and the second-layer history filter that
the API cannot provide when the payload is capped at 50 nids.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..services.feed import build_feed

router = APIRouter()

ID_MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def format_viewed_at(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        month_name = ID_MONTHS[dt.month - 1]
        return f"{dt.day} {month_name} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return iso_str


SOURCE_LABELS = {
    "popular": "Berita populer",
    "cold-session": "Rekomendasi dari riwayat bacaanmu",
    "warm": "Rekomendasi berdasarkan profil dataset demo",
}


@router.get("/", response_class=HTMLResponse)
async def feed(request: Request):
    result = await build_feed(request)
    return request.app.state.templates.TemplateResponse(
        request, "feed.html",
        {
            "config": request.app.state.config,
            "user": request.state.user,
            "csrf": request.state.csrf,
            "articles": result.articles,
            "label": SOURCE_LABELS[result.mode],
            "mode": result.mode,
            "notice": result.notice,
            "active_page": "feed",
        },
    )


@router.get("/histori", response_class=HTMLResponse)
async def history(request: Request):
    store = request.app.state.store
    user_id = int(request.state.user["id"])
    rows = store.history_rows(user_id)
    client = request.app.state.client
    articles = []
    seen: set[str] = set()
    for row in rows:
        nid = row["nid"]
        if nid in seen:
            continue
        seen.add(nid)
        detail = await client.article(nid)
        if detail is None:
            continue
        articles.append({**detail, "viewed_at": format_viewed_at(row["created_at"]),
                         "source": row["source"]})
    return request.app.state.templates.TemplateResponse(
        request, "history.html",
        {"config": request.app.state.config, "user": request.state.user,
         "csrf": request.state.csrf, "articles": articles, "active_page": "history"},
    )
