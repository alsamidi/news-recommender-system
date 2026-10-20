"""Web application: auth, feed, article detail, history.

Mounts the frozen recommendation API at "/" **last**, so the contract paths
(/health, /recommend, /similar/{nid}, /article/{nid}) stay exactly as published.

The frozen app's lifespan does NOT run when mounted, so this app owns the model
load via the approved `load_recommender()` seam (D13).
"""
from __future__ import annotations

import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# src/ on sys.path so `api.main` and `models.*` resolve like the tests do.
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import api.main as frozen  # noqa: E402  (path set above)

from .config import load_config  # noqa: E402
from .db import Store  # noqa: E402
from .csrf import issue as issue_csrf  # noqa: E402
from .security import token_hash  # noqa: E402
from .clients.rec_api import RecClient  # noqa: E402
from .services.popular import Popularity  # noqa: E402
from .throttle import LoginThrottle  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own everything the mounted frozen app cannot do for itself."""
    cfg = load_config()
    app.state.csrf_secret = secrets.token_bytes(32)
    app.state.throttle = LoginThrottle()
    store = Store(cfg.db_path)
    store.init_schema()

    # Frozen model: load via the additive seam (mounted lifespan never runs).
    rec = frozen.load_recommender()

    # Popularity: computed once here, never at import time.
    catalog_nids = set(rec._d["full_nids"])
    popularity = Popularity.build(catalog_nids=catalog_nids)

    app.state.config = cfg
    app.state.store = store
    app.state.popularity = popularity
    app.state.client = RecClient(app)
    try:
        yield
    finally:
        await app.state.client.aclose()
        frozen.rec = None
        frozen.demo_presets = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="News Recommender Web",
        lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,   # D16: no web /docs
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    from .routes import article, auth, feed

    app.include_router(auth.router)
    app.include_router(feed.router)
    app.include_router(article.router)

    @app.middleware("http")
    async def attach_session(request: Request, call_next):
        """Resolve the session and enforce auth on protected paths.

        Runs before routing so every handler can rely on request.state.user.
        """
        request.state.user = None
        request.state.csrf = None
        cookie = request.cookies.get("session")
        if cookie:
            row = request.app.state.store.get_session(token_hash(cookie))
            if row is not None:
                request.state.user = request.app.state.store.get_user(int(row["user_id"]))
                request.state.csrf = row["csrf_token"]

        path = request.url.path
        protected = path == "/" or path.startswith(("/berita/", "/histori"))
        if protected and request.state.user is None:
            return RedirectResponse("/login", status_code=303)

        # Anonymous forms need a signed token before a session exists.
        anon_form = path in {"/register", "/login"} and request.state.user is None
        nonce_to_set = None
        token_to_set = None
        if anon_form:
            token, nonce_to_set = issue_csrf(request)
            request.state.csrf = token
            if request.cookies.get("csrf_token") != token:
                token_to_set = token

        response = await call_next(request)

        if nonce_to_set:
            response.set_cookie(
                "csrf_nonce", nonce_to_set, httponly=True, samesite="lax", path="/"
            )
        if token_to_set:
            response.set_cookie(
                "csrf_token", token_to_set, httponly=True, samesite="lax", path="/"
            )
        return response

    # Mount LAST: frozen API keeps its exact published paths.
    app.mount("/", frozen.app)
    return app


app = create_app()
