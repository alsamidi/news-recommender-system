"""Article detail + view recording.

View semantics (approved 2026-10-20):
- one view per successfully displayed detail page
- refresh / re-navigation creates a new view
- prefetch/background fetch alone creates none
- no user+nid time-window dedupe
- unknown nid => no row
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..clients.rec_api import RecAPIError
from ..services.catalog_meta import attach_article_meta
from ..services.stats import attach_reader_counts

router = APIRouter()


@router.get("/berita/{nid}", response_class=HTMLResponse)
async def article_detail(request: Request, nid: str):
    client = request.app.state.client
    store = request.app.state.store

    try:
        article = await client.article(nid)
    except RecAPIError:
        return _error(request, "Sistem rekomendasi sedang disiapkan. Coba lagi sebentar.",
                      status_code=503)

    if article is None:
        # No interaction row for a missing article.
        return _error(request, "Berita tidak ditemukan.", status_code=404)

    # Record exactly one view for this displayed page load.
    user_id = int(request.state.user["id"])
    source = request.query_params.get("from", "direct")
    if source not in {"feed", "similar", "history", "direct"}:
        source = "direct"
    store.add_view(user_id, nid, source)

    try:
        related = await client.similar(nid, top_k=5)
    except RecAPIError:
        related = []

    # Same counts as the feed: the related cards are the same kind of card and
    # a reader comparing them deserves the same context.
    related = [r for r in related if r["nid"] != nid]
    attach_reader_counts(request, related)
    attach_article_meta(request.app.state.article_meta, related, cards=True)
    # Detail page keeps the full body (cards=False): only meta is merged.
    attach_article_meta(request.app.state.article_meta, [article], cards=False)

    return request.app.state.templates.TemplateResponse(
        request, "article.html",
        {
            "config": request.app.state.config,
            "user": request.state.user,
            "csrf": request.state.csrf,
            "article": article,
            "related": related,
        },
    )


def _error(request: Request, message: str, status_code: int):
    return request.app.state.templates.TemplateResponse(
        request, "error.html",
        {"config": request.app.state.config, "user": request.state.user,
         "csrf": request.state.csrf, "message": message, "code": status_code},
        status_code=status_code,
    )
