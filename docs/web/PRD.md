# PRD — Web Layer for the News Recommender

> ## ⚠ SUPERSEDED — ARCHIVE ONLY
>
> **Do not implement from this file.** The only active PRD is
> **`PRD_Web_Rekomendasi_Berita.md`**, which removes topic onboarding from the
> MVP (§5.2, §18) and locks the remaining decisions.
>
> This file is retained **only** because its §8 fact table (`F-01`…`F-24`,
> measured repo facts) is still cited by the other documents. Scope, features,
> and decisions here are void. Visual authority is `DESIGN.md`.
>
> Acceptance criteria in this document used the old `AC-xx` namespace, which is
> **retired**. Current namespaces: `PRD-AC-xx` and `TEST-AC-xxx`.

Status: **SUPERSEDED (archive).**
Draft date: 2026-10-20.
Decision owner: thesis author (Aldimas Jaya Dinaga N.P).

Companion documents: `UX_FLOWS.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`,
`RECOMMENDATION_INTEGRATION.md`, `ACCEPTANCE_CRITERIA.md`.

---

## 1. Summary

This repository already contains a frozen recommendation model and a v1.0.0
serving API. What is missing is **a product people can actually use**: users
cannot sign up, read articles, leave a trail, or receive recommendations under
their own account.

This PRD defines a **demonstrable MVP** on top of that frozen API — without
retraining the model and without changing the API contract.

## 2. Problem

The current demo (`src/api/templates/demo.html`) is a **technical viewer**: the
user types a dataset `user_id` or pastes a list of `nid` values. That cannot be
demoed as a product and produces no user data.

Consequences:

- No notion of "my account" — every demo depends on dataset fixtures.
- No reading history, so there is no evidence of stored interactions.
- No path from "brand-new user" to a sensible recommendation.
- Features present in Figma (register, login, topic picker, feed, article
  detail, rating, "people also read") have no counterpart in code.

## 3. Goals

1. Users can **register** and **log in**.
2. Users can **read articles** from the available catalog.
3. Every read is **stored as an interaction** (history).
4. Users can **view their history**.
5. Users receive **recommendations** sourced from either:
   - a **dataset profile** (persona with training history), or
   - **session history** (new user / no training history).
6. Model, α, artifacts, and evaluation numbers **do not change**.

## 4. Non-Goals (MVP)

- Retraining or re-tuning the model on new user data.
- Real-time recommendations that alter model weights per user.
- Semantic search, AI summarization, translation, or TTS.
- Push notifications, email, or a social feed.
- Native mobile applications.
- A production admin/analytics panel.
- Star ratings as a **model signal** (see §7 decision D3).

## 5. Target Users

| Persona | Description | Need |
|---------|-------------|------|
| **New reader** | Registers, has no history | Initial recommendations from chosen topics / session |
| **Returning reader** | Has read several articles | Recommendations from session history; visible history |
| **Dataset persona** | Demo account mapped to a MIND `user_id` | Warm recommendations (ALS personalization) |
| **Evaluator** | Thesis examiner | Repeatable end-to-end flow with consistent numbers |

## 6. Feature Scope

### 6.1 Required (MVP)

| ID | Feature | Source |
|----|---------|--------|
| F1 | Account registration (name, email, password) | Figma `Register` |
| F2 | Login / logout | Figma `Login` |
| F3 | Landing page leading into the feed | Figma `Landing` |
| F4 | Topic selection (onboarding) | Figma `Pilih Topik` |
| F5 | Recommendation feed (top-10) | Figma `rekomendasi awal` |
| F6 | Article detail (title, abstract, category) | Figma `isi berita` |
| F7 | Store read interactions (history) | *absent from Figma* — MVP need |
| F8 | Reading history page | *absent from Figma* — MVP need |
| F9 | "People also read" / similar block | Figma `isi berita` + `halaman collaborative filtering` |

### 6.2 Should Have (post-MVP)

| ID | Feature | Note |
|----|---------|------|
| S1 | Star rating on articles | Figma has it; does not affect the model (D3) |
| S2 | Profile page | Figma has a `Profil` icon |
| S3 | Title search | Figma has `Telusuri` |
| S4 | Onboarding tour / "why was this recommended" | — |

### 6.3 Out of Scope

| ID | Figma feature | Reason |
|----|---------------|--------|
| X1 | `Sumber: detik.com` on article cards | Dataset stores no publisher/source (F-16) |
| X2 | Article thumbnails | Dataset stores no images (F-16) |
| X3 | `Penulis:` and `Tanggal:` on detail | Dataset stores no author or publication date (F-16) |
| X4 | Topics "Teknologi Informasi", "Pendidikan", "Politik" as categories | Not present in dataset `category` (F-14) |

## 7. Decisions Awaiting Approval

| ID | Question | Options | Recommendation |
|----|----------|---------|----------------|
| **D1** | How are new users mapped to recommendations? | (a) session from reading history only; (b) session + seeds from chosen topics; (c) map to a dataset persona | **(b)** — Figma topics can be mapped to `category`, then used as session seeds |
| **D2** | Does "choose topic" change scores, or only pick seeds? | (a) filter candidates by category (changes ranking); (b) only pick seed `nid` values for `history` | **(b)** — (a) means new ranking logic outside the frozen model |
| **D3** | Do star ratings influence recommendations? | (a) yes, as a signal; (b) no, UI only | **(b)** for MVP — (a) requires a new model |
| **D4** | Do we need a dataset-persona demo account? | (a) not needed; (b) one demo account mapped to a warm `user_id`; (c) a picker listing many dataset users | **(c)**, superseding (b) on 2026-10-21 (D28) — demonstrates the warm path without retraining, and lets a reviewer compare several profiles. Gated by `WEB_PERSONA_PICKER`, off by default |
| **D5** | Storage | (a) SQLite; (b) Postgres (`psycopg2`/`pgvector` already in requirements) | **(a)** for MVP — zero extra services |
| **D6** | Login session | (a) signed cookie session; (b) JWT | **(a)** — stdlib + `itsdangerous` already available |
| **D7** | Is cross-device history required? | (a) yes; (b) no | **(b)** for MVP |

## 8. Facts Found in the Repository

Referenced as `F-xx` and reused across documents.

| ID | Fact | Evidence |
|----|------|----------|
| F-01 | API v1.0.0 is frozen: 4 routes (`/health`, `/recommend`, `/similar/{nid}`, `/article/{nid}`) | `docs/API_CONTRACT.md`, `docs/openapi.json`, `test_openapi_contract_surface` |
| F-02 | Serving α = 0.4, no per-request override | `configs/hybrid.yaml`, `serving_alpha()`, `test_serving_alpha_matches_table_b_winner` |
| F-03 | Catalog has 93,698 rows, 65,238 unique `nid`; 28,460 `nid` duplicated across splits | measurement of `data/processed/news_processed.parquet` |
| F-04 | ALS space holds 3,394 items (≈5.2% of unique `nid`); 15,608 users have ALS factors | `models/als_model.pkl` |
| F-05 | 50,000 train users, only 15,608 have ALS factors (min 5 interactions) | `configs/als.yaml`, `als_model.pkl` |
| F-06 | Warm `POST /recommend` requires a `user_id` with ALS factors; otherwise 404 | `UnknownUserError`, `src/api/main.py` |
| F-07 | Cold path uses `history: [nid]`; with no ALS item it falls back to content-only, `mode` stays `cold-session` | `recommend_session`, `test_cold_fallback_no_als_item_is_pure_content` |
| F-08 | `/similar/{nid}` returns TF-IDF neighbours, excluding the query article | `HybridRecommender.similar` |
| F-09 | `/article/{nid}` returns `nid, title, abstract, category, subcategory` | `ArticleDetailResponse` |
| F-10 | No auth, accounts, sessions, or persistence exist today | grep of `src/` |
| F-11 | No migrations or DB schema; `psycopg2`/`pgvector` exist only in requirements | `requirements.txt` |
| F-12 | Tests: 26 passing, including serving-vs-evaluator parity | `pytest -q` |
| F-13 | Scores are min-max normalized per request → not comparable across requests | `_minmax`, `infer.py` |
| F-14 | Catalog `category` = 18 MIND values: `autos, entertainment, finance, foodanddrink, games, health, kids, lifestyle, middleeast, movies, music, news, northamerica, sports, travel, tv, video, weather`. **No** `technology`, `education`, or `politics` | parquet measurement |
| F-15 | 270 `subcategory` values; 5.0% of rows have no `abstract` | parquet measurement |
| F-16 | Catalog stores no URL, publisher, author, publication date, or image. `MINDsmall_train/news.tsv` has `assets.msn.com` URLs, but they **do not** reach the parquet | `build_locked.py`, parquet columns |
| F-17 | Interactions = clicks (`label==1`) in `behaviors.tsv`; `weight` = click count per user–nid pair | `build_interactions` |
| F-18 | Dev split: 110,745 click rows, median 1 click/user, p90 = 4 | `error_coverage.json`, parquet |
| F-19 | 88.1% of dev users have no train history; 62.7% of dev-relevant items never appear in train interactions | `models/error_coverage.json` |
| F-20 | Warm: 2,858 eligible, 2,000 sampled. Cold: 22,703 usable sessions, 2,000 sampled; 836 without ALS items | `models/*_eval.json` |
| F-21 | NDCG@10: warm α=0.4 → 0.00208; cold subset n=1,164 α=0.4 → 0.00921 | `docs/metrics_source_of_truth.md` |
| F-22 | Frozen artifacts are not committed; load takes ~6.1 s, RSS ~503 MB | measurement |
| F-23 | Serving latency: warm/cold ~6–7 ms; `/similar` ~70 ms | local measurement |
| F-24 | An uncommitted change exists in `src/api/main.py` (line 172) that is **whitespace only**; tokens are identical | `git diff` |
| F-25 | 15,608 dataset users have ALS factors and can serve as personas; the picker lists a capped subset (default 50) | `recommender_data["user_map"]`, `WEB_PERSONA_PICKER_LIMIT` |
| F-26 | Only 9,100 of 65,238 catalogue nids (13.9%) appear in train+dev interactions at all; 86.1% have no recorded click | measurement of `interactions_{train,dev}.parquet` |
| F-27 | Per-nid unique readers: median 3, p90 67, max 7,994 across the dataset sample | measurement, `services/stats.py` |
| F-28 | The web layer writes no schema change for reader counts: `unique_readers()` is a query over the existing `interactions` table | `SCHEMA_VERSION == 1` |

## 9. Figma ↔ Data Fit (Summary)

Full detail in `UX_FLOWS.md` §5.

| Figma feature | Available in data? | MVP decision |
|---------------|--------------------|--------------|
| Article title | ✅ `title` | Use |
| Article body/summary | ✅ `abstract` (5% empty) | Use; provide fallback |
| Category | ✅ `category` (18 values) | Use |
| Subcategory | ✅ `subcategory` (270 values) | Render when present |
| Star rating | ❌ not in data | UI-only (D3), or defer (S1) |
| Source `detik.com` | ❌ | **Remove from MVP design** |
| Thumbnail image | ❌ | **Remove / neutral placeholder** |
| Author, date | ❌ | **Remove from MVP design** |
| Topic Olahraga | ✅ ≈ `sports` | Map |
| Topic Kesehatan | ✅ `health` | Map |
| Topic Politik | ⚠️ no category; ≈ subset of `news` | **Needs decision** (D1/D2) |
| Topic Teknologi Informasi | ⚠️ absent; scattered | **Needs decision** |
| Topic Pendidikan | ⚠️ absent; scattered | **Needs decision** |
| "Orang lain juga membaca" | ⚠️ not a model feature | Replace with "Berita serupa" via `/similar` |
| "Liked by similar users" | ⚠️ only implicit in ALS | Do not surface as a separate claim |

## 10. MVP Success Metrics

Not model metrics (the model is frozen). These are product metrics for the demo:

1. A new user can complete register → login → feed **without ever touching a
   `nid` or `user_id`**. (Topic selection was dropped from the MVP; see §7 D1
   and the note in `ACCEPTANCE_CRITERIA.md`.)
2. Every opened article is recorded as an interaction row and appears in history.
3. The feed changes after history grows (recommendations react to the session).
4. Every displayed recommendation is traceable to a real `/recommend` response
   (no invented scores).
5. `pytest` still shows 26+ passing and `audit_freeze.sh` still passes.

## 11. Product-Level Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| "Smart recommendation" expectations vs NDCG 0.002 | Examiner thinks the system is broken | Show catalog context and evaluation caveats on an "About" page |
| Cold start with no ALS items | Weak suggestions | Content-only fallback already exists; label the mode in the UI |
| Figma topics absent from data | Confusing onboarding | Restrict to real categories (D1) |
| Ratings with no effect | Wrong expectations | Label explicitly or defer |
| Thin metadata (no image/date) | UI feels bare | Text-first card design; never fabricate data |
