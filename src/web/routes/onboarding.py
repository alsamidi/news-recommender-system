"""Topic onboarding for 0-view users (PRD addendum v1.2 §6).

Flow: register -> (once) `/onboarding/topik` -> feed.

Invariants this module owns:
- The screen is shown **once** per account (C2). `users.topics_prompted_at`
  records that it was shown, so "skipped" and "never asked" stay distinct.
  Without that marker a 0-view user who pressed "Lewati" would be asked again
  on every visit.
- Skipping is always available and has no side effect beyond the marker (C2).
- Submitting zero chips is **skip** (m = 0 has no quota; `ceil(10/0)` is
  undefined), so the endpoint cannot store an empty preference that would
  later look like a chosen topic set.
- Only labels in the measured chip set are accepted, server-side (C7/§3);
  the form is not trusted. Preferences are profile data, never events (C5).
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..csrf import require_csrf
from ..services.topics import (MAX_TOPICS, TOPIC_LABELS, TopicUnavailable,
                               canonicalize)

router = APIRouter()


def _render(request: Request, status_code: int = 200, error: str | None = None):
    return request.app.state.templates.TemplateResponse(
        request, "onboarding_topics.html",
        {
            "config": request.app.state.config,
            "user": request.state.user,
            "csrf": request.state.csrf,
            "chips": TOPIC_LABELS,
            "max_topics": MAX_TOPICS,
            "error": error,
            "active_page": None,
        },
        status_code=status_code,
    )


@router.get("/onboarding/topik", response_class=HTMLResponse)
async def onboarding_form(request: Request):
    """Offer the chip screen once, to a signed-in 0-view user."""
    user = request.state.user
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["topics_prompted_at"] is not None:
        # Already answered or skipped: never ask twice.
        return RedirectResponse("/", status_code=303)
    return _render(request)


@router.post("/onboarding/topik", response_class=HTMLResponse)
async def onboarding_submit(
    request: Request,
    csrf_token: str = Form(""),
    lewati: str = Form(""),
    topik: list[str] = Form(default=[]),
):
    require_csrf(request, csrf_token)
    user = request.state.user
    if not user:
        return RedirectResponse("/login", status_code=303)

    store = request.app.state.store
    user_id = int(user["id"])

    # "Lewati" and an empty selection are the same outcome: no preference.
    if lewati or not topik:
        store.mark_topics_prompted(user_id)
        return RedirectResponse("/", status_code=303)

    try:
        labels = canonicalize(topik)
    except TopicUnavailable:
        return _render(request, status_code=400,
                       error="Topik tidak dikenal. Pilih dari daftar yang tersedia.")
    if len(labels) > MAX_TOPICS:
        return _render(request, status_code=400,
                       error=f"Pilih maksimal {MAX_TOPICS} topik.")

    store.replace_user_topics(user_id, labels)
    store.mark_topics_prompted(user_id)
    return RedirectResponse("/", status_code=303)
