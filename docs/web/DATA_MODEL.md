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

**Corpus note (2026-10-27, PRD v1.1):** phase-2 aktif memakai katalog korpus
Indonesia + parquet interaksi simulasi (path final di
`data/DATASET_LOCK_INDO.md`). Keduanya masuk boundary read-only yang sama;
artefak era MIND tetap beku sebagai riset v1.

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

### 2.3 Active corpus schema (Indo — phase 2, drafted 2026-10-27)

Skema §2–2.2 di atas adalah fakta era MIND (riset v1, beku). Korpus aktif
(sumber: `data/DATASET_LOCK_INDO.md`) membangun parquet katalog sendiri dengan
kolom:

| Column | Note |
|--------|------|
| `nid` | `'I' + sha1(url)[:10]` — deterministik, tanpa tabrakan format `N...` |
| `title` | dari `Judul` |
| `content` | konten penuh setelah strip boilerplate portal (pengganti peran `abstract`) |
| `processed_text` | teks pra-proses TF-IDF; **never show to users** (aturan sama) |
| `category` | hasil pemetaan seksi URL (100% cakupan terukur); bukan tag portal |
| `source` | `kompas` / `tempo` / `detik` |
| `published_at` | dari `Waktu` (parser bulan-Indonesia, 100% terparse) |
| `split` | temporal; cutoff final dicatat di lock (TBC sampai generator v1) |

Tidak ada `abstract`/`subcategory`. Baris: 80.472 mentah → **67.381 unik**
(dup URL 100% identik — terukur, beda dari kasus MIND di §2.1).

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
| `created_at` | TEXT | NOT NULL | ISO-8601 UTC |
| `topics_prompted_at` | TEXT | NULL | Set when the topic onboarding was shown (see §3.3bis) |

Notes:
- **No persona binding** (v1.3): `users.persona_user_id` was dropped by an
  idempotent migration, together with the accounts that carried it. The app has
  no roles; a user is a user.
- Accounts are created only by public registration or the persona-free login.

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
| `user_topics` | **Present since PRD v1.2** (see §3.3bis below). `DESIGN.md`'s `topic-filter-rail` marketing component remains unused — the chips are a plain form control, not that rail. |
| `ratings` | Ratings/likes are out of MVP scope (PRD §5.2). |
| `articles_cache` | Article data is read from the catalog/API, never copied (PRD §8.4). |
| `recommendation_scores` | Scores are min-max normalized per request and must not be persisted (F-13). |

### 3.3bis `user_topics` (PRD v1.2)

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | INTEGER | PK AUTOINCREMENT |
| `user_id` | INTEGER | NOT NULL, FK `users(id)` ON DELETE CASCADE |
| `label` | TEXT | NOT NULL; must be one of the 12 measured chips (`src/web/services/topics.py`) |
| `position` | INTEGER | NOT NULL; **canonical chip order**, not click order |
| `created_at` | TEXT | NOT NULL, ISO-8601 UTC |

`UNIQUE (user_id, label)`; at most 3 rows per user (validated server-side).
`position` is canonical because an HTML multi-select submits values in DOM
order — storing "click order" is impossible without client-side JS, and a
column that disagrees with what the browser sent would make the feed
nondeterministic (TEST-AC-262).

Also v1.2: `users.topics_prompted_at TEXT NULL` — set when the onboarding
screen is shown or skipped. Without it, "skipped" and "never asked" both look
like zero `user_topics` rows, and the once-only promise (C2) cannot be kept.
The column is added by an idempotent `PRAGMA table_info`-guarded `ALTER TABLE`
in `Store.init_schema`, because `CREATE TABLE IF NOT EXISTS` is a no-op on an
existing table.

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
| `history` (cold) | `SELECT DISTINCT nid FROM interactions WHERE user_id=? ORDER BY MAX(created_at) DESC LIMIT 50` |
| `top_k` | Constant **30** (not 12) — leaves room to reach 12 cards after filtering |
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
| Copies of `title`/`content`/`abstract` | Duplicating the frozen catalog → divergence risk |
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
