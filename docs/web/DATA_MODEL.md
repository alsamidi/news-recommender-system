# Data Model — Web Layer for the News Recommender

Status: **DRAFT — not approved.**
Date: 2026-10-20.

This document defines the **new data owned by the web application**. Research
data (catalog, dataset interactions, model artifacts) is **not modified** and is
not duplicated here.

---

## 1. Data Boundaries

| Layer | Source | May the web layer write? |
|-------|--------|--------------------------|
| News catalog | `data/processed/news_processed.parquet` | ❌ read only |
| Dataset interactions (train/dev) | `data/processed/interactions_{train,dev}.parquet` | ❌ read only |
| Model artifacts | `models/*` | ❌ read only |
| **Application data** | `data/web.db` (SQLite) | ✅ owned by the web layer |

**Rule:** the application **never writes** to parquet files or `models/`. Web
user interactions are stored separately in SQLite so the research dataset stays
byte-identical to the frozen snapshot.

## 2. Catalog Schema (READ ONLY — fact)

Source: `data/processed/news_processed.parquet`, 93,698 rows.

| Column | Type | Nulls | Note |
|--------|------|-------|------|
| `nid` | string | 0 | MIND article ID, e.g. `N55528`. **65,238 unique** |
| `title` | string | 0 | Indonesian title (xMIND) |
| `abstract` | string | 4,687 (5.0%) | Indonesian summary/body |
| `processed_text` | string | 0 | Stemmed text for TF-IDF; **never show to users** |
| `category` | string | 0 | 18 MIND values |
| `subcategory` | string | 0 | 270 values |
| `split` | string | 0 | `train` (51,282) / `dev` (42,416) |

### 2.1 Duplication That Must Be Handled

93,698 rows ≠ 65,238 articles. **28,460 `nid` appear twice**: one `train` row and
one `dev` row with **identical** `title`, `abstract`, `category`, `subcategory`
(verified: 0 differences).

Implications:
- Every rendered list must **dedupe by `nid`**.
- The API already dedupes for presentation (`_select`), but the web layer must
  stay defensive because manual joins can reintroduce duplicates.
- Never present "93,698 news items" to users as the article count; that is a row
  count, not an article count.

### 2.2 `category` Values That Actually Exist

```
autos, entertainment, finance, foodanddrink, games, health, kids, lifestyle,
middleeast, movies, music, news, northamerica, sports, travel, tv, video, weather
```

There is no `technology`, `education`, or `politics`. This is why topic
onboarding was dropped from the MVP (see `UX_FLOWS.md` §5.3 and
`PRD_Web_Rekomendasi_Berita.md` §5.2): 3 of the 5 Figma topic chips have no
valid `category` counterpart.

## 3. Application Schema (NEW — SQLite)

All tables use an internal `INTEGER PRIMARY KEY`; `nid` is stored as `TEXT` with
**no** foreign key to the parquet (parquet is not an SQL table).

### 3.1 `users`

| Column | Type | Constraint | Note |
|--------|------|-----------|------|
| `id` | INTEGER | PK AUTOINCREMENT | |
| `name` | TEXT | NOT NULL | Display name |
| `email` | TEXT | NOT NULL UNIQUE (case-insensitive) | Stored lowercase |
| `password_hash` | TEXT | NOT NULL | Format `scrypt$n$r$p$salt_b64$hash_b64` |
| `persona_user_id` | TEXT | NULL | Dataset `user_id` for the demo account (D4). NULL for regular users |
| `created_at` | TEXT | NOT NULL | ISO-8601 UTC |

Notes:
- `persona_user_id` is populated by two paths, both idempotent:
  1. `python -m src.web.seed_persona`, which reads `WEB_DEMO_PERSONA_USER_ID`
     (see `.env.example`).
  2. The passwordless picker at `/login/persona` (D28), which calls
     `Store.ensure_persona_user()` for the chosen id. Only reachable when
     `WEB_PERSONA_PICKER` is set.
  Never through public registration, never at startup.
- Both paths upsert rather than insert, so re-running either cannot create a
  second account for the same dataset user. The picker keys on
  `persona_user_id`; the seed command keys on `email`.
- Accounts created by the picker get a random password hash that is never
  shown to anyone: they are entered by choosing them, not by typing a
  credential.
- There is no `role` column in the MVP (no admin).

### 3.2 `sessions`

| Column | Type | Constraint | Note |
|--------|------|-----------|------|
| `id` | INTEGER | PK | |
| `token_hash` | TEXT | NOT NULL UNIQUE | SHA-256 of the cookie token (raw token never stored) |
| `user_id` | INTEGER | NOT NULL → `users(id)` ON DELETE CASCADE | |
| `created_at` | TEXT | NOT NULL | |
| `expires_at` | TEXT | NOT NULL | `created_at` + 7 days (approved) |
| `csrf_token` | TEXT | NOT NULL | Per-session CSRF token |

### 3.3 `interactions`

| Column | Type | Constraint | Note |
|--------|------|-----------|------|
| `id` | INTEGER | PK | |
| `user_id` | INTEGER | NOT NULL → `users(id)` ON DELETE CASCADE | |
| `nid` | TEXT | NOT NULL | Must exist in the catalog (validated by the app) |
| `event` | TEXT | NOT NULL | `view` only in the MVP |
| `created_at` | TEXT | NOT NULL | ISO-8601 UTC (storage is always UTC; the history page renders it as WIB, UTC+7) |
| `source` | TEXT | NOT NULL | `feed`, `similar`, `history`, `direct` |

Indexes: `(user_id, created_at DESC)`, `(user_id, nid)`.

**View semantics (approved 2026-10-20):**

| Rule | Detail |
|------|--------|
| A view is | one article-detail page **successfully displayed** via user navigation |
| Counting | exactly one row per displayed page load |
| Refresh / re-navigation | creates a **new** view (new row) |
| Prefetch / background fetch | **must not** create a view |
| Time-window dedupe | **not used** — no `(user, nid, window)` suppression |
| Retries | if implemented, carry a unique `event_id` with a uniqueness constraint for idempotency |
| Missing article (404) | **no** row is written |

Consequence for the schema: if event retries are introduced, add a nullable
`event_id TEXT UNIQUE` column. The MVP does not need it, because the write path
is a single synchronous insert after a successful render.

Important notes:
- **No UNIQUE (user_id, nid)** — a user may open the same article repeatedly;
  history shows events, not a set.
- To build the `history` payload for `/recommend`, the app takes the **last
  unique `nid` by most recent occurrence**, not every row.
- The `value` column from the earlier draft is **removed**: there is no rating
  feature in the MVP (PRD §5.2).

### 3.4 Deliberately absent tables

| Table | Why it does not exist |
|-------|-----------------------|
| `user_topics` | Topic selection is out of MVP scope (PRD §5.2, §18). `DESIGN.md`'s `topic-filter-rail` component is therefore also unused. |
| `ratings` | Ratings/likes are out of MVP scope (PRD §5.2). |
| `articles_cache` | Article data is read from the catalog/API, never copied (PRD §8.4). |
| `recommendation_scores` | Scores are min-max normalized per request and must not be persisted (F-13). |

### 3.5 `schema_migrations`

| Column | Type | Constraint |
|--------|------|-----------|
| `version` | INTEGER | PK |
| `applied_at` | TEXT | NOT NULL |

Migrations run idempotently at startup (`CREATE TABLE IF NOT EXISTS`).

## 4. Relationships

```
users 1 ──── N sessions
users 1 ──── N interactions

interactions.nid ─ ─ ─► catalog (logical, no SQL FK)
users.persona_user_id ─► ALS user_map (logical, no SQL FK)
```

## 5. Data Lifecycle

| Event | Effect |
|-------|--------|
| Register | INSERT `users`; new session |
| Login | INSERT `sessions`; new cookie token |
| Logout | DELETE `sessions` |
| Open detail | INSERT `interactions` (`event='view'`) |
| Delete account (S2) | CASCADE removes all derived data |
| Session expiry | Row deleted when read after `expires_at` has passed |

## 6. Mapping to API Payloads

| API need | Web data source |
|----------|-----------------|
| `user_id` (warm) | `users.persona_user_id` |
| `history` (cold) | `SELECT DISTINCT nid FROM interactions WHERE user_id=? ORDER BY MAX(created_at) DESC LIMIT 50` |
| `top_k` | Constant **30** (not 10) — leaves room to reach 10 cards after filtering |
| `nid` for `/article`, `/similar` | From the URL, validated against the catalog |

Rules in detail: `RECOMMENDATION_INTEGRATION.md`.

## 7. Integrity and Validation

| Rule | Enforcement |
|------|-------------|
| `nid` must exist in the catalog | Check against the catalog set before INSERT; otherwise 404 |
| Email unique (case-insensitive) | UNIQUE index on `lower(email)` |
| Passwords never stored in plaintext | Only `password_hash` |
| Session tokens never stored in plaintext | Only `token_hash` |
| History belongs to the requesting user | Every query filtered by the session's `user_id`, never by a parameter |
| No personal data in URLs | Internal `user_id` never appears in a path |

## 8. Volume Estimates

| Table | Rows (demo estimate) | Size |
|-------|----------------------|------|
| `users` | < 100 | < 100 KB |
| `sessions` | < 500 | < 1 MB |
| `interactions` | < 100,000 | < 20 MB |

SQLite is more than sufficient. There is no high-concurrency requirement.

## 9. Deliberately NOT Stored

| Data | Reason |
|------|--------|
| Recommendation scores | Min-max per request → meaningless across time (F-13) |
| Per-web-user ALS factors | Web users have none; the pseudo-user is computed by the API per request |
| Copies of `title`/`abstract` | Duplicating the frozen catalog → divergence risk |
| `processed_text` in the UI | Stemmed text, not meant for humans |
| Search history | No search feature in the MVP |
| IP / user-agent | Not needed; avoids personal data |

## 10. Open Data Decisions

| ID | Question | Recommendation |
|----|----------|----------------|
All data decisions are **settled** (2026-10-20).

| ID | Decision | Status |
|----|----------|--------|
| D17 | Keep all `interactions`; no automatic purge | ✅ Approved |
| D18 | Keep the `source` column | ✅ Approved |
| D19 | History payload: 50 unique `nid`, then filter against the full history | ✅ Approved |
| D20 | No `articles_cache` table | ✅ Approved |
| — | Session TTL **7 days** | ✅ Approved |
| — | `data/web.db*` is gitignored and must never be tracked | ✅ Required |
