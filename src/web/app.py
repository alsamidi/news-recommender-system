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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
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
from .services.catalog_meta import build_article_meta, categories_of  # noqa: E402
from .services.textview import build_source_urls  # noqa: E402
from .services.popular import Popularity  # noqa: E402
from .services.stats import build_dataset_readers  # noqa: E402
from .throttle import IP_MAX_FAILURES, LoginThrottle  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


class RevalidatingStaticFiles(StaticFiles):
    """Static files that browsers must revalidate before reuse.

    Starlette sends ETag and Last-Modified but no Cache-Control, so browsers
    fall back to heuristic freshness and can serve a stale stylesheet long
    after it changed -- which is how a fixed layout kept looking broken until
    the page was opened in a private window. `no-cache` does not disable
    caching: it requires a revalidation, and the ETag turns that into a 304
    when the file has not changed. Cheap, and it cannot go stale.
    """

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own everything the mounted frozen app cannot do for itself."""
    cfg = load_config()
    # A fixed secret keeps outstanding anonymous form tokens valid across a
    # restart and across workers. Without one, fall back to a per-process
    # random value, which is fine for a single-process local demo.
    app.state.csrf_secret = (
        cfg.csrf_secret.encode() if cfg.csrf_secret else secrets.token_bytes(32)
    )
    app.state.throttle = LoginThrottle()
    # Same limiter, looser budget. One IP is not one person: a campus NAT, an
    # office or a mobile carrier gateway fronts many users, so the per-IP
    # ceiling must sit well above the per-email one or a shared address locks
    # out people who never mistyped anything. 30 in 15 minutes still stops
    # automated guessing across accounts (2 attempts/minute) while leaving a
    # roomful of legitimate users unaffected.
    app.state.ip_throttle = LoginThrottle(max_failures=IP_MAX_FAILURES)
    store = Store(cfg.db_path)
    store.init_schema()

    # Frozen model: load via the additive seam (mounted lifespan never runs).
    rec = frozen.load_recommender()

    # Popularity: computed once here, never at import time.
    catalog_nids = set(rec._d["full_nids"])
    popularity = Popularity.build(catalog_nids=catalog_nids)

    app.state.config = cfg
    app.state.recommender_data = rec._d
    # Display metadata (source + publication date) for the active corpus,
    # built once at startup like the popularity list. Empty under the MIND
    # era, which has neither field.
    app.state.article_meta = build_article_meta()
    # `nid -> category`, used by the topic feed to slice the frozen popularity
    # ranking (PRD addendum v1.2 C4). Derived once; no second catalog read.
    app.state.topic_categories = categories_of(app.state.article_meta)
    # Original portal link per nid, reconstructed from the raw CSV (the catalog
    # has no `url` column and adding one would break its recorded sha256).
    app.state.source_urls = build_source_urls(
        set(rec._d["full_nids"])) if rec._d.get("era") == "indo" else {}
    # Reader-count label: the dataset sample is simulated under the indo
    # corpus, so the card must not claim "MIND" there (PRD v1.1 §18;
    # TEST-AC-256 is about labelling the source, not about the word MIND).
    era = rec._d.get("era")
    app.state.dataset_readers_label = (
        "× via MIND" if era == "mind" else "× via simulasi")
    app.state.dataset_readers_title = (
        "Pembaca unik di sampel dataset MIND (train+dev)" if era == "mind"
        else "Akun simulasi unik yang membaca berita ini di dataset "
             "(train+dev); bukan pembaca nyata")
    # Unique dataset readers per nid, built once (~0.25 s) from the frozen
    # interaction parquet. Read-only for the life of the process.
    app.state.dataset_readers = build_dataset_readers()
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
    app.mount("/static", RevalidatingStaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    from .routes import article, auth, feed, onboarding

    app.include_router(auth.router)
    app.include_router(onboarding.router)
    app.include_router(feed.router)
    app.include_router(article.router)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        """Render a page for browser requests instead of raw JSON.

        The frozen API is mounted separately and handles its own exceptions,
        so its JSON error shape is untouched by this handler. Here the client
        is a person looking at a form: a 403 that reads
        {"detail":"CSRF token tidak valid"} is a dead end with no way back.
        """
        if request.headers.get("accept", "").startswith(("application/json",)):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return request.app.state.templates.TemplateResponse(
            request, "error.html",
            {"config": request.app.state.config, "user": request.state.user,
             "csrf": getattr(request.state, "csrf", None),
             "message": exc.detail, "code": exc.status_code},
            status_code=exc.status_code,
        )

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
        anon_form = (
            path in {"/register", "/login", "/landing"}
            and request.state.user is None
        )
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
                "csrf_nonce", nonce_to_set, httponly=True, samesite="lax", path="/",
                secure=app.state.config.secure_cookies,
            )
        if token_to_set:
            response.set_cookie(
                "csrf_token", token_to_set, httponly=True, samesite="lax", path="/",
                secure=app.state.config.secure_cookies,
            )
        return response

    # Mount LAST: frozen API keeps its exact published paths.
    app.mount("/", frozen.app)
    return app


app = create_app()
