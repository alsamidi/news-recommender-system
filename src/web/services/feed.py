"""Feed assembly: the only place that decides which API path to use."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fastapi import Request

from ..clients.rec_api import RecAPIError

logger = logging.getLogger(__name__)


@dataclass
class FeedResult:
    articles: list[dict] = field(default_factory=list)
    mode: str = "popular"          # popular | cold-session | warm
    notice: str | None = None


def _dedupe_keep_order(rows: list[dict], limit: int) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        nid = row["nid"]
        if nid in seen:
            continue
        seen.add(nid)
        out.append(row)
        if len(out) == limit:
            break
    return out


async def _fetch_articles(client, nids: list[str]) -> list[dict]:
    """Populate title/category for nids that came from the API.

    /recommend already returns these fields, so this is only used for the
    popular path where there is no model response to read from.
    """
    out = []
    for nid in nids:
        detail = await client.article(nid)
        if detail is not None:
            out.append(detail)
    return out


async def _attach_details(client, rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        if row.get("abstract") is not None:
            out.append(row)
        else:
            detail = await client.article(row["nid"])
            if detail is not None:
                merged = {**detail, **row}
                if detail.get("abstract"):
                    merged["abstract"] = detail["abstract"]
                out.append(merged)
            else:
                out.append(row)
    return out


async def build_feed(request: Request) -> FeedResult:
    cfg = request.app.state.config
    store = request.app.state.store
    client = request.app.state.client
    popularity = request.app.state.popularity
    user = request.state.user
    user_id = int(user["id"])

    full_history = store.all_history_nids(user_id)
    persona_id = user["persona_user_id"]

    # 1) Persona -> warm
    if persona_id:
        try:
            body = await client.recommend({"user_id": persona_id, "top_k": cfg.rec_top_k})
            rows = [a for a in body["recommendations"] if a["nid"] not in full_history]
            deduped = _dedupe_keep_order(rows, cfg.feed_limit)
            return FeedResult(await _attach_details(client, deduped), "warm")
        except RecAPIError as exc:
            # Invalid persona seed: fall through to history, then popular.
            notice = "Profil dataset demo tidak tersedia; menampilkan rekomendasi lain."
            result = await _history_or_popular(request, user_id, full_history, client,
                                               popularity, cfg)
            result.notice = notice
            return result
        except Exception as exc:  # noqa: BLE001 - surface, never swallow silently
            logger.exception("persona feed failed for user %s: %s", user_id, exc)
            notice = "Terjadi kendala saat memuat profil demo; menampilkan rekomendasi lain."
            result = await _history_or_popular(request, user_id, full_history, client,
                                               popularity, cfg)
            result.notice = notice
            return result

    return await _history_or_popular(request, user_id, full_history, client,
                                     popularity, cfg)


async def _history_or_popular(request, user_id: int, full_history: set[str],
                              client, popularity, cfg) -> FeedResult:
    history = request.app.state.store.history_nids(user_id, cfg.history_limit)
    if history:
        try:
            body = await client.recommend({"history": history, "top_k": cfg.rec_top_k})
            rows = [a for a in body["recommendations"] if a["nid"] not in full_history]
            deduped = _dedupe_keep_order(rows, cfg.feed_limit)
            return FeedResult(await _attach_details(client, deduped), "cold-session")
        except RecAPIError:
            # e.g. every history nid unknown to the catalog: fall back.
            pass

    # Popular path: no model call.
    nids = [n for n in popularity.top(cfg.rec_top_k) if n not in full_history]
    nids = nids[:cfg.feed_limit]
    rows = await _fetch_articles(client, nids)
    return FeedResult(_dedupe_keep_order(rows, cfg.feed_limit), "popular")
