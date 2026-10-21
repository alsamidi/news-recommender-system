"""Persona list for the passwordless demo picker.

The picker exists so a demo can jump straight into a dataset profile without
seeding an account by hand. It is gated behind WEB_PERSONA_PICKER, because the
page signs a visitor into whichever account they click with no credential.

Only users that actually have ALS factors are listed: a persona without them
falls back to the cold path, which defeats the point of the picker.
"""
from __future__ import annotations

from fastapi import Request


def eligible_personas(request: Request, limit: int) -> list[dict]:
    """Dataset users that have ALS factors, sorted, with their read counts."""
    data = request.app.state.recommender_data
    user_map = data["user_map"]
    train_full = data["train_full"]

    out = []
    for user_id in sorted(user_map):
        if len(out) >= limit:
            break
        out.append({
            "user_id": user_id,
            # How many catalogue items the profile is built from. Shown so the
            # list is not a wall of identical strings.
            "items": len(train_full.get(user_id, ())),
        })
    return out


def persona_count(request: Request) -> int:
    return len(request.app.state.recommender_data["user_map"])
