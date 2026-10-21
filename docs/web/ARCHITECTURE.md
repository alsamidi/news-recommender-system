# Architecture — Web Layer for the News Recommender

Status: **DRAFT — not approved.**
Date: 2026-10-20.

---

## 1. Architectural Principles

1. **The model is a frozen black box.** The web layer never computes scores
   itself. The only scoring path is `HybridRecommender`
   (`src/models/hybrid/infer.py`), reached through API v1.0.0.
2. **The API contract does not change.** The four frozen routes stay at the same
   paths with the same schemas.
3. **Clear separation:** web app (product) vs API app (research). The API works
   without the web app; the web app must not break the API.
4. **No mandatory new services.** SQLite + filesystem is enough for the MVP.
5. **Everything testable is tested.** Routing logic (persona vs. history vs.
   popular), history selection, and filtering must have unit tests that do not
   load the model.

## 2. Component Overview

```
┌──────────────────────────────────────────────────────────────┐
│  Browser                                                      │
│  (HTML + minimal CSS/JS, server-rendered Jinja2)              │
└───────────────┬──────────────────────────────────────────────┘
                │ HTTP (session cookie)
┌───────────────▼──────────────────────────────────────────────┐
│  Web App  (NEW)  src/web/                                     │
│  ├─ routes/auth      register, login, persona, logout         │
│  ├─ routes/feed      feed, history                            │
│  ├─ routes/article   detail (proxy + record interaction)      │
│  ├─ services/feed    persona → history → popular              │
│  ├─ services/stats   unique reader counts (dataset + app)     │
│  ├─ db.Store         SQLite access                            │
│  ├─ templates/       Jinja2                                   │
│  └─ static/          CSS/JS                                   │
└───────┬──────────────────────────────┬───────────────────────┘
        │ read/write                   │ internal HTTP (in-process)
┌───────▼──────────────┐   ┌───────────▼───────────────────────┐
│  SQLite data/web.db  │   │  API v1.0.0  (FROZEN)             │
│  users, sessions,    │   │  src/api/main.py                  │
│  interactions        │   │  /health /recommend               │
│                      │   │  /similar/{nid} /article/{nid}    │
└──────────────────────┘   └───────────┬───────────────────────┘
                                       │
                           ┌───────────▼───────────────────────┐
                           │  HybridRecommender (FROZEN)       │
                           │  TF-IDF + ALS, α=0.4              │
                           │  models/* artifacts (no retrain)  │
                           └───────────────────────────────────┘
```

## 3. Proposed Directory Structure

Aligned with `PRD_Web_Rekomendasi_Berita.md` (no topic onboarding) and
`DESIGN.md` (token-driven styling).

```
src/web/
  __init__.py
  app.py                # web FastAPI app + lifespan owning the model
  config.py             # DB path, session TTL, history cap, persona seed, flags
  security.py           # password hashing, session tokens, CSRF token helpers
  csrf.py               # signed anonymous tokens + require_csrf
  throttle.py           # login throttle (per email and per IP)
  db.py                 # SQLite connection + schema + queries
  seed_persona.py       # idempotent persona account seeding (CLI)
  routes/
    auth.py             # /register /login /login/persona /logout
    feed.py             # / (feed), /histori
    article.py          # /berita/{nid}
  services/
    feed.py             # decision tree: persona -> history -> popular
    popular.py          # train click-count popularity for the no-history feed
    persona.py          # eligible dataset users for the picker
    stats.py            # unique reader counts (dataset + app)
  clients/
    rec_api.py          # thin client to the frozen API (in-process)
  templates/
    base.html, landing.html, login.html, persona_picker.html,
    register.html, feed.html, article.html, history.html, error.html
  static/
    tokens.css          # DESIGN.md tokens as CSS custom properties
    app.css             # layout + components built from tokens
    goodnews.svg        # wordmark, inlined into the nav
tests/web/
  test_auth.py, test_feed.py, test_popular.py, test_article.py,
  test_units.py, test_design_tokens.py, test_traceability.py
```

There is no `schemas.py` and no `services/store.py`: SQLite access lives on the
`Store` class in `db.py`, and the web layer reuses the frozen API's Pydantic
models rather than duplicating them.

Notes:
- `onboarding.py` / `topics.py` / `topics.html` from the earlier draft are
  **removed** — topic selection is out of MVP scope (PRD §5.2).
- `tokens.css` is generated **by hand** from the `DESIGN.md` front matter. Do
  not add a build step or a CDN; the token file is committed as plain CSS.
- `src/api/` is **not touched**. `src/web/` is a new package.

### 3.1 Design token pipeline

`DESIGN.md` (YAML front matter) → `src/web/static/tokens.css` (CSS custom
properties) → `app.css` consumes variables only.

```
--color-primary: #181d26;
--color-ink: #181d26;
--color-body: #333840;
--color-muted: #41454d;
--color-canvas: #ffffff;
--color-surface-soft: #f8fafc;
--color-surface-strong: #e0e2e6;
--color-signature-coral: #aa2d00;
--color-signature-cream: #f5e9d4;
--color-info-border: #458fff;
--radius-sm: 6px;  --radius-md: 10px;  --radius-lg: 12px;
--space-xs: 8px; --space-sm: 12px; --space-md: 16px;
--space-lg: 24px; --space-xl: 32px; --space-xxl: 48px;
```

Approved aliases and overrides (decisions D25–D27, 2026-10-20):

```css
/* D25 — error color; DESIGN.md has no danger token */
--color-error: var(--color-signature-coral);   /* #aa2d00, 6.81:1 on white */

/* D26 — article body readability; tokens themselves are NOT changed */
--type-article-size: 16px;
--type-article-leading: 1.6;
```

```css
/* applied only to the article body */
.article-body { font-size: var(--type-article-size);
                line-height: var(--type-article-leading);
                max-width: 70ch; }
```

Rules:
- `app.css` must not contain raw hex values; only `var(--…)` references. This
  makes `TEST-AC-201`/`TEST-AC-202` mechanically checkable.
- No `@import` from a remote origin. No `@font-face` with a remote `src`.
- Font stack is the local system stack (`AGENTS.md` §5.1); `DESIGN.md`'s Haas
  fonts are licensed and unavailable.
- `--color-error` is an **alias**, not a new color. `tokens.css` must contain
  exactly one occurrence of `#aa2d00`.
- Hover rules (D27) may only reference these variables; no `transform`,
  `scale`, or `box-shadow`, and transitions ≤ 120 ms.

### 3.2 Server-rendered rendering rules

- Jinja2 templates receive **already-ordered** recommendation lists; templates
  must not sort, slice by score, or filter.
- The template layer renders at most 10 cards; the cap is applied in
  `services/recs.py`, not in Jinja.
- Empty/loading/error states are separate template blocks, not inline
  conditionals scattered across pages.

## 4. Critical Integration Decisions

### 4.1 How to Call the Frozen API

Three options:

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| A | HTTP loopback (`httpx` to `127.0.0.1:8000`) | Full isolation; API genuinely separate | Two processes; ports; network latency |
| B | In-process: call handler functions directly | Single process | Bypasses FastAPI validation; easy to drift from the contract |
| C | **Web app mounts the API app** (one process, two apps) | Single process, contract still enforced, identical API paths | Needs special lifespan handling (§4.2) |

**Recommendation: C**, with an internal client using `httpx.ASGITransport` so
requests genuinely pass through FastAPI (real validation and status codes)
without opening a socket.

**Already verified in this repository** (probe, 2026-10-20):

- `web.mount("/", frozen.app)` keeps the frozen paths exactly intact
  (`/health`, `/recommend`, `/similar/{nid}`, `/article/{nid}`).
- Web routes registered **before** the mount win over the mount on the same path
  (e.g. `GET /` and `GET /berita/{nid}`).
- The frozen app's OpenAPI still lists only those 4 routes; the web app has its
  own separate OpenAPI.

### 4.2 Trap: a Mounted Sub-App's Lifespan Does NOT Run

**This is a measured finding, not a guess.** Probe:

```python
web = FastAPI()
web.mount("/", frozen.app)
with TestClient(web) as c:
    frozen.rec is not None      # -> False
    c.get("/health").status_code  # -> 503 "recommender not loaded"
```

FastAPI/Starlette **does not** run the `lifespan` of a mounted sub-app.
`src/api/main.py` loads the model in its `lifespan` and stores it in the module
global `rec`, which `get_rec()` reads.

**Consequence:** if unhandled, every `/recommend` call returns 503.

**Verified fix:** the web app loads the model in its own lifespan and populates
the frozen app's globals:

```python
@asynccontextmanager
async def lifespan(app):
    r = HybridRecommender.load()          # frozen artifacts, no retraining
    frozen.rec = r                        # read by get_rec()
    frozen.demo_presets = frozen.resolve_presets(r._d)
    yield
    frozen.rec = None
    frozen.demo_presets = None

web = FastAPI(lifespan=lifespan)
# ... register web routes ...
web.mount("/", frozen.app)                # mount LAST
```

Probe result: `/health` → 200, `/recommend` warm/cold → 200, `/berita/{nid}` →
web route, `/` → web route.

**Decision D13 (APPROVED 2026-10-20): option B — add a narrow seam in
`src/api/main.py`.** Setting another module's globals is rejected.

### 4.2.1 The permitted change (strict limits)

The only allowed addition is one **purely additive** function. No existing line
may be modified, moved, or deleted.

```python
def load_recommender():
    """Load frozen artifacts and install them for serving.

    Additive seam for embedders (the web app) that mount this app and
    therefore do not receive this module's lifespan. Returns the instance.
    """
    global rec, demo_presets
    rec = HybridRecommender.load()
    demo_presets = resolve_presets(rec._d)
    return rec
```

The web app calls `frozen.load_recommender()` from **its own** lifespan. The
frozen `lifespan` stays untouched, so standalone `uvicorn src.api.main:app`
behaves exactly as before.

**Hard limits — a change is rejected if it does any of these:**

| Forbidden | Reason |
|-----------|--------|
| Adding, removing, renaming, or re-pathing any route | API contract v1.0.0 |
| Changing any Pydantic model or field | contract |
| Changing `FINAL_ALPHA`, `serving_alpha()`, or `HybridRecommender` | α = 0.4 is frozen |
| Changing scoring, ordering, masking, or dedupe | would break evaluator parity |
| Refactoring imports, moving code, reformatting the file | not needed; inflates the diff |
| Rewriting `lifespan` to call the new function | optional at most; if done, a **single-line** replacement only |
| Any change to `docs/openapi.json` | must remain byte-identical |

**Proof required before merge (all four):**

1. `python -m pytest -q` → 26 passed (unchanged count).
2. `bash scripts/audit_freeze.sh` → `RESEARCH FREEZE AUDIT PASSED`.
3. `docs/openapi.json` identical to `app.openapi()` (regenerate and diff).
4. `test_openapi_contract_surface` passes; `git diff src/api/main.py` shows
   **additions only** (no `-` lines except a deliberate single-line lifespan
   call, if you choose it).

If any of these fail, revert the seam and fall back to option A (globals),
documenting the reason.

### 4.3 Internal Client

```python
# src/web/clients/rec_api.py
transport = httpx.ASGITransport(app=web)   # combined app
client = httpx.AsyncClient(transport=transport, base_url="http://web")
```

Benefit: Pydantic validation, genuine 400/404/422/503 status codes, no logic
duplication. The client **must not** touch `HybridRecommender` directly.

## 5. Recommendation Data Flow

```
Feed request
  → does the user have a dataset persona mapping?
      yes → POST /recommend {"user_id": <persona>}          → mode warm
      no  → is there reading history?
          yes → POST /recommend {"history": [last 50 nid]}   → cold-session
          no  → 10 popular articles (labeled "Berita populer")  (D8)

  After any model response:
      → drop nid present in the user's FULL history
      → dedupe by nid
      → keep API order, take at most 10
      → render ONE source label (TEST-AC-051)

  Persona 404 (invalid seed):
      → fall back to history if present
      → otherwise controlled error page, never a raw traceback
```

Every path yields a `list[ArticleResponse]` of the same shape.
Detail: `RECOMMENDATION_INTEGRATION.md`.

## 6. Security and Sessions

| Aspect | Draft decision |
|--------|----------------|
| Password hashing | `hashlib.scrypt` (stdlib), per-user salt, documented parameters |
| Session cookie | `HttpOnly`, `SameSite=Lax`, random 32-byte value; only its **hash** is stored in the DB |
| **Session TTL** | **7 days** (approved 2026-10-20). Expired rows are deleted on read |
| CSRF | Per-session token on POST forms |
| Password policy | Minimum 8 characters; no complex composition rules |
| Login rate limit | Simple: count failures per email per 15 minutes (in-memory is enough for the MVP) |
| Personal data | Only name + email + password hash; no telemetry |
| Account enumeration | Uniform failure message on login |

Rejected alternatives for the MVP: OAuth, stateless JWT, 2FA, email verification
(all add dependencies or services with no demo benefit).

### 6.1 Demo persona provisioning

Approved 2026-10-20. The demo account is **never** created at startup and
**never** lives in source code.

| Concern | Rule |
|---------|------|
| Which dataset user | `WEB_DEMO_PERSONA_USER_ID` (e.g. `U10045`), read from the environment |
| Account email | `WEB_DEMO_PERSONA_EMAIL` — local value, documented in `.env.example` |
| Account password | `WEB_DEMO_PERSONA_PASSWORD` — supplied locally at run time, never committed |
| Creation | Explicit command: `python -m src.web.seed_persona` |
| Idempotency | Re-running must **not** create a second account; it updates the existing row |
| Validation | The seed command calls the API once with the persona id; if the result is 404, abort with a clear message |
| Startup | No seeding, no demo user creation, no extra work |
| Missing env var | Persona seeding is skipped explicitly; the app still runs with normal users only |

`U10045` is verified to have ALS factors (2,858 eligible warm users; returns 10
recommendations).

`.env.example` (committed, no secrets):

```
# Demo persona — copy to .env and fill locally. Never commit .env.
WEB_DEMO_PERSONA_USER_ID=U10045
WEB_DEMO_PERSONA_EMAIL=
WEB_DEMO_PERSONA_PASSWORD=
```

`.env` must be listed in `.gitignore` (it already is).

## 7. Performance

Measured figures (F-22, F-23):

| Operation | Time |
|-----------|------|
| Model load at startup | ~6.1 s, RSS ~503 MB |
| `POST /recommend` warm | ~6 ms |
| `POST /recommend` cold (history 5–400 nid) | ~6–7 ms |
| `GET /similar` | ~70 ms |

Implications:
- The model loads **once** at startup, never per request.
- Long history does not slow things down meaningfully (flat up to 400 nid).
- `/similar` is ~10× slower; cap `top_k` and cache per `nid` if needed.

### 7.1 State built at startup

`app.state` is populated once in the lifespan, because everything below is
read-only afterwards and would be wasteful to rebuild per request:

| State | Built by | Cost | Used by |
|-------|----------|------|---------|
| `recommender_data` | `HybridRecommender.load()` | part of the ~8 s model load | persona picker (eligibility), feed |
| `dataset_readers` | `services.stats.build_dataset_readers()` | ~0.6 s, 9,100 entries | reader counts on cards |
| `popularity` | `Popularity.build()` | one pass over train interactions | the no-history feed |
| `throttle` / `ip_throttle` | `LoginThrottle()` | trivial | login |
| `csrf_secret` | config, or 32 random bytes | trivial | anonymous form tokens |

`dataset_readers` maps `nid` → count of distinct dataset `user_id`s, built from
the frozen interaction parquet at startup. It is a dict lookup at request time.

Per-request cost added by reader counts: one grouped SQLite query per page,
chunked at 500 ids because SQLite caps host parameters at 999.

Memory note: `recommender_data` exposes the already-loaded `_d` dict rather
than copying it, so the picker does not add a second copy of the model.

## 8. Observability

- One log line per web request: `method path status ms user_id?`.
- No personal data in logs beyond the internal `user_id`.
- The API's own `/health` is used as-is for health checks.

## 9. Alternatives Considered

| Alternative | Why rejected (for the MVP) |
|-------------|----------------------------|
| Separate React/Vue SPA | Adds build tooling; Figma is simple; SSR Jinja2 suffices |
| Postgres + pgvector | Requires a DB service; pgvector is unused by the model (in-memory TF-IDF) |
| Standalone recommendation microservice | A frozen API already exists; adds a process with no benefit |
| Persisting scores to the DB | Scores are unstable across requests (min-max per request) → meaningless |
| Adding a new vector table | Duplicates frozen artifacts; risks divergence |

## 10. Model Integration Risks

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | Sub-app lifespan does not run → 503 | All recommendations dead | §4.2 (verified) |
| R2 | New users have no ALS factors | 404 if `user_id` is sent incorrectly | Router always sends `history` for non-personas; handle 404 |
| R3 | History contains only non-ALS items | Quality drops (content-only) | Detect from the response (`mode`), label in the UI |
| R4 | `nid` duplicated across splits | Duplicate cards in the UI | Dedupe by `nid` in the web layer (API already dedupes; this is a second layer) |
| R5 | Scores not comparable across requests | Misleading if compared | Do not render raw scores; or label them explicitly |
| R6 | 5.0% of articles have no `abstract` | Empty detail page | Conditional rendering |
| R7 | 6 s startup + 503 MB | Slow cold start | Load once; health check; document it |
| R8 | Accidental changes to frozen files | Freeze audit fails | Run `audit_freeze.sh` locally/CI before committing |
| R9 | `data/processed/*.parquet` not committed | Fresh deploy has no data | Document prerequisites; never rely on git |
| R10 | Mounting the frozen app exposes the old `GET /` demo | Two `/` pages | Web `/` route registered first → wins (verified) |
| R11 | Truncated history → old articles resurface | Users see articles they already read | Second-layer filter against the full history; `top_k=30` then take 10 (`RECOMMENDATION_INTEGRATION.md` §5.4) |
| R12 | `DESIGN.md` assumes images and editorial metadata | Fake content in the UI | Data availability wins; cards render text-only (`AGENTS.md` §6.1) |
| R13 | `DESIGN.md` fonts (Haas) are licensed and unavailable | Silent webfont download / CDN dependency | Local system stack only; PRD §12 forbids CDN (`AGENTS.md` §5.1) |
| R14 | `hairline` (#dddddd) used as input border | 1.36:1 — fails WCAG 1.4.11 | Use `muted`/`info-border` for control boundaries (TEST-AC-232) |
| R15 | `DESIGN.md` has no error color | Ad-hoc red hexes appear | **D25 approved:** `--color-error` aliases `signature-coral` (#aa2d00); no other red allowed (TEST-AC-236) |
| R16 | Token drift between `DESIGN.md` and `app.css` | Visual inconsistency | `tokens.css` is the only place hex values exist; `app.css` uses `var()` (TEST-AC-201/202) |

## 11. Test Plan

| Level | Content |
|-------|---------|
| Unit | `popular.py` (popularity ordering + determinism), `recs.py` (route selection, full-history filter), `security.py` (hash/verify), `store.py` (CRUD) |
| Integration | Register→login→feed→detail→history, with the model loaded once (session-scoped fixture) |
| Parity | Payload sent by the web layer == payload accepted by `RecommendRequest`; results not reordered |
| Contract | `test_openapi_contract_surface` still passes; `docs/openapi.json` unchanged |
| Regression | `pytest -q` ≥ 26 passing; `audit_freeze.sh` passes |

## 12. Open Architecture Decisions

All architecture decisions are **settled** (2026-10-20). None remain open.

| ID | Decision | Status |
|----|----------|--------|
| D13 | Additive `load_recommender()` seam in `src/api/main.py`, under the strict limits in §4.2.1 | ✅ Approved |
| D14 | **One process** — web app mounts the frozen API at `/` (last) | ✅ Approved |
| D15 | **SQLite** (`data/web.db`) | ✅ Approved |
| D16 | Web app does **not** expose `/docs`; only the frozen API has docs | ✅ Approved |

If implementation discovers a need outside these four, stop and record the
blocker — do not widen the architecture silently.
