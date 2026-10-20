# Web MVP — Runbook

How to run, seed, and verify the web layer. Scope and behaviour are defined by
`PRD_Web_Rekomendasi_Berita.md`; this file is operational only.

---

## 1. Prerequisites

The web layer sits on top of the frozen research stack. It needs:

| Requirement | Why | Verify |
|-------------|-----|--------|
| `data/processed/news_processed.parquet` | catalog (93,698 rows) | `ls -l data/processed/` |
| `data/processed/interactions_train.parquet` | popularity ranking | same |
| `models/tfidf_baseline.pkl`, `models/als_model.pkl`, `models/als_{user,item}_factors.npy` | model artifacts | `ls -l models/` |
| `configs/hybrid.yaml` | serving α = 0.4 | `cat configs/hybrid.yaml` |
| Python 3.12 venv | runtime | `source venv/bin/activate` |

Raw datasets (`MINDsmall_*`, `xMINDsmall_*`) are **not** required at runtime;
only the processed Parquet files are.

These files are gitignored. A "clean checkout" therefore means **checkout plus
these inputs**, not checkout alone.

---

## 2. Install

```bash
source venv/bin/activate
pip install -r requirements.txt      # now includes python-multipart
```

`python-multipart` is required by FastAPI's `Form()` parsing and was added for
the web layer.

---

## 3. Environment

Copy the template and fill in local values:

```bash
cp .env.example .env
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `WEB_DB_PATH` | `data/web.db` | SQLite file (gitignored) |
| `WEB_SESSION_TTL_DAYS` | `7` | session lifetime |
| `WEB_HISTORY_LIMIT` | `50` | unique nids sent to `/recommend` |
| `WEB_FEED_LIMIT` | `10` | cards rendered |
| `WEB_REC_TOP_K` | `30` | `top_k` requested from the API |
| `WEB_DEMO_PERSONA_USER_ID` | — | dataset user with ALS factors (e.g. `U10045`) |
| `WEB_DEMO_PERSONA_EMAIL` | — | local login email for the demo account |
| `WEB_DEMO_PERSONA_PASSWORD` | — | local password (never committed) |

`WEB_REC_TOP_K` must be ≥ `WEB_FEED_LIMIT` and within the API's 1–100 range;
startup fails fast otherwise.

---

## 4. Start

```bash
uvicorn web.app:app --app-dir src --port 8000
```

`--app-dir src` is required so `web.*`, `api.*`, and `models.*` resolve without
installing the package.

Startup does three things, once:

1. initialises the SQLite schema (idempotent),
2. loads the frozen recommender via `api.main.load_recommender()`,
3. builds the popularity ranking from `interactions_train.parquet`.

A missing Parquet file or a malformed config aborts startup with a clear
message — the app never serves a half-initialised feed.

---

## 5. Seed the demo persona

```bash
python -m src.web.seed_persona
```

- Reads the three `WEB_DEMO_PERSONA_*` variables.
- Verifies the dataset user has ALS factors **before** writing anything.
- Idempotent: re-running updates the existing row, never duplicates it.
- Never runs at startup; a missing variable set simply skips provisioning.

Verified working seed: `U10045`. It is one of the **15,608** train users that
have ALS factors (the 2,858 figure elsewhere is the smaller set that is *also*
eligible for evaluation, which persona seeding does not require).

---

## 6. Verify

```bash
# web behaviour, isolated throwaway database
bash scripts/smoke_web.sh

# research stack must remain untouched
python -m pytest -q                # 77 passed
bash scripts/audit_freeze.sh       # RESEARCH FREEZE AUDIT PASSED
bash scripts/smoke_demo.sh         # original API + demo UI proof
```

`smoke_web.sh` exercises two scenarios:

| Scenario | Steps |
|----------|-------|
| A — new user | register → popular feed (10 cards) → open 2 articles → 2 `view` rows → cold feed excludes them → history lists them |
| B — persona | seed → login → warm feed (10 cards) → open detail |

It also asserts the frozen `/health` payload is unchanged, anonymous access is
redirected, and no traceback reaches the log. It runs on a temporary database
and never touches `data/web.db`.

---

## 7. Routes

| Path | Auth | Purpose |
|------|------|---------|
| `GET /` | yes | feed (popular / cold-session / warm) |
| `GET /berita/{nid}` | yes | article detail; records one `view` |
| `GET /histori` | yes | reading history, newest first |
| `GET /login`, `GET /register` | no | forms |
| `POST /login`, `POST /register`, `POST /logout` | — | with CSRF |
| `/health`, `/recommend`, `/similar/{nid}`, `/article/{nid}` | — | **frozen API, mounted unchanged** |
| `/static/*` | no | CSS |

The web app exposes no OpenAPI schema (`docs_url=None`). Note that `/docs` still
returns 200 because the **frozen API's** docs are reachable through the mount.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `503 recommender not loaded` | model load skipped | ensure the web lifespan ran; do not mount the frozen app yourself without calling `load_recommender()` |
| `PopularityUnavailable: popularity source missing` | train Parquet absent | generate `data/processed/interactions_train.parquet` |
| `RuntimeError: Form data requires "python-multipart"` | dependency missing | `pip install -r requirements.txt` |
| `CSRF token tidak valid` | stale cookie or missing field | reload the form; each GET issues the token |
| Empty feed for a new user | popularity empty or catalog mismatch | check startup log for `PopularityUnavailable` |
| Persona seed exits 3 | dataset user has no ALS factors | pick one of the eligible users; `U10045` is verified |

---

## 9. Data safety

- `data/web.db*` and `.env` are gitignored. Verify with
  `git check-ignore -v data/web.db .env`.
- The web layer never writes to `data/processed/*.parquet` or `models/`.
- Passwords are stored as `scrypt$...`; session tokens only as SHA-256 hashes.
- Clearing state = delete `data/web.db` and restart.
