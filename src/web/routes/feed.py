"""Feed routing: persona (warm) -> history (cold) -> popular.

Implements the approved decision tree and the second-layer history filter that
the API cannot provide when the payload is capped at 50 nids.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..services.feed import build_feed
from ..services.stats import attach_reader_counts

router = APIRouter()

ID_MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# WIB is UTC+7 year-round; Indonesia has no daylight saving, so a fixed offset
# is exact rather than an approximation. Stored timestamps stay UTC -- only the
# presentation converts.
WIB = timezone(timedelta(hours=7), "WIB")

def format_viewed_at(iso_str: str) -> str:
    """Render a stored UTC timestamp as WIB (UTC+7).

    The stored value carries its own offset, so astimezone converts from
    whatever was written instead of assuming. A naive value is treated as UTC,
    which is what utcnow() writes.
    """
    try:
        dt = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return iso_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(WIB)
    return f"{dt.day} {ID_MONTHS[dt.month - 1]} {dt.year}, {dt.hour:02d}:{dt.minute:02d} WIB"


SOURCE_LABELS = {
    "popular": "Berita populer",
    "cold-session": "Rekomendasi dari riwayat bacaanmu",
    "warm": "Rekomendasi berdasarkan profil dataset demo",
}


@router.get("/", response_class=HTMLResponse)
async def feed(request: Request):
    result = await build_feed(request)
    attach_reader_counts(request, result.articles)
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
    attach_reader_counts(request, articles)
    return request.app.state.templates.TemplateResponse(
        request, "history.html",
        {"config": request.app.state.config, "user": request.state.user,
         "csrf": request.state.csrf, "articles": articles, "active_page": "history"},
    )
