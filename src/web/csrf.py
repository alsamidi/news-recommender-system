"""CSRF protection using a signed, server-verifiable token.

Design note: the earlier version compared the submitted token against a plain
`csrf` cookie. That is insecure — an attacker who can plant a cookie (subdomain
injection, sibling-service cookie) can supply both halves of the pair and
register/login a victim into an attacker-controlled account.

Fix: the pre-session token is an HMAC-signed value bound to a random nonce
cookie. The attacker cannot forge the signature without the server secret, so
planting a cookie is not enough.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request

from .security import csrf_matches

_NONCE_COOKIE = "csrf_nonce"
_TOKEN_COOKIE = "csrf_token"
_TTL_SECONDS = 2 * 60 * 60  # pre-session forms only; sessions use DB tokens


def _secret(request: Request) -> bytes:
    """Per-process secret, created once at startup."""
    secret = getattr(request.app.state, "csrf_secret", None)
    if secret is None:
        raise RuntimeError("csrf secret not initialised")
    return secret


def sign(request: Request, nonce: str, issued_at: int | None = None) -> str:
    ts = int(time.time()) if issued_at is None else issued_at
    msg = f"{nonce}:{ts}".encode()
    mac = hmac.new(_secret(request), msg, hashlib.sha256).hexdigest()
    return f"{ts}.{mac}"


def _verify_signature(request: Request, token: str, nonce: str) -> bool:
    try:
        ts_s, mac = token.split(".", 1)
        ts = int(ts_s)
    except (ValueError, AttributeError):
        return False
    if abs(time.time() - ts) > _TTL_SECONDS:
        return False
    expected = hmac.new(_secret(request), f"{nonce}:{ts}".encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, mac)


def issue(request: Request) -> tuple[str, str | None]:
    """Return (form_token, nonce_to_set) for an anonymous form.

    Reuse the existing signed token while its timestamp is still inside the
    freshness window. Signing a fresh token per GET would invalidate the value
    already rendered into an open form as soon as the clock ticks.
    """
    nonce = request.cookies.get(_NONCE_COOKIE)
    existing = request.cookies.get(_TOKEN_COOKIE)
    new_cookie = None

    if not nonce:
        nonce = secrets.token_urlsafe(16)
        new_cookie = nonce

    if existing and _verify_signature(request, existing, nonce):
        return existing, new_cookie

    return sign(request, nonce), new_cookie


def require_csrf(request: Request, submitted: str | None) -> None:
    """Reject unless the token is valid for this request.

    Session users: compare against the token stored with their session.
    Anonymous forms: require a valid HMAC over the nonce cookie.
    """
    session_csrf = getattr(request.state, "csrf", None)
    if session_csrf:
        if not csrf_matches(submitted, session_csrf):
            raise HTTPException(status_code=403, detail="CSRF token tidak valid")
        return

    nonce = request.cookies.get(_NONCE_COOKIE)
    if not submitted or not nonce or not _verify_signature(request, submitted, nonce):
        raise HTTPException(status_code=403, detail="CSRF token tidak valid")
