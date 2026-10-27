# Acceptance Criteria — Web Layer for the News Recommender

Status: **DRAFT — not approved.**
Date: 2026-10-20.
Revised: **2026-10-27 — addendum transisi korpus (PRD v1.1)** lihat §L.

Each criterion is written to be **objectively testable**.

**ID namespace.** This file uses **`TEST-AC-001` … `TEST-AC-999`**. The product
acceptance criteria in `PRD_Web_Rekomendasi_Berita.md` §14 use a *different*
namespace, **`PRD-AC-01` … `PRD-AC-54`**. Never cite a bare `AC-xx`: always
state the namespace, so a criterion can never be confused between documents.

- Test criteria here (`TEST-AC-xxx`) are the detailed, runnable checks.
- Product criteria there (`PRD-AC-xx`) are the scope-level Definition of Done.
- Design criteria were folded into this namespace as `TEST-AC-2xx`.

**[P]** marks MVP-mandatory criteria; **[S]** marks the next stage.

**Authoritative sources.** Scope and behavior come from
`PRD_Web_Rekomendasi_Berita.md` (the only active PRD — `PRD.md` is superseded
and archived). Visual rules come from `DESIGN.md`. Facts `F-xx` are defined in
the archived `PRD.md` §8 and remain valid as measurements.

---

## A. Research Integrity (must never be violated)

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-001 **[P]** | API contract v1.0.0 is unchanged | `test_openapi_contract_surface` passes; `docs/openapi.json` identical to `app.openapi()` |
| TEST-AC-002 **[P]** | The four frozen routes stay at the same paths with the same schemas | `GET /health`, `POST /recommend`, `GET /similar/{nid}`, `GET /article/{nid}` respond per `docs/API_CONTRACT.md` |
| TEST-AC-003 **[P]** | α stays 0.4 and has no per-request override | `test_serving_alpha_matches_table_b_winner` passes; `RecommendRequest` has no `alpha` property |
| TEST-AC-004 **[P]** | Model artifacts are unchanged | `git status` clean for `models/`; mtimes unchanged; `audit_freeze.sh` passes |
| TEST-AC-005 **[P]** | Evaluation numbers are unchanged | `bash scripts/audit_freeze.sh` → `RESEARCH FREEZE AUDIT PASSED` |
| TEST-AC-006 **[P]** | No retraining at startup or per request | `src/web/` imports no `src/models/*/train.py`; startup ≈ 6 s (load only) |
| TEST-AC-007 **[P]** | Research datasets are not modified | `data/processed/*.parquet` mtimes unchanged; no `to_parquet` in `src/web/` |
| TEST-AC-008 **[P]** | Research tests do not shrink | `python -m pytest -q` ≥ 26 passing |

## B. Authentication

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-010 **[P]** | Users can register with name, email, password | Register form POST → 303 to **`/onboarding/topik`** (v1.2: skippable topic screen, once); one `users` row added |
| TEST-AC-011 **[P]** | Duplicate email is rejected with a clear message | Register twice with the same email → form error, no new row |
| TEST-AC-012 **[P]** | Passwords are stored hashed, never in plaintext | DB query: `password_hash` does not contain the password; format `scrypt$...` |
| TEST-AC-013 **[P]** | Password and confirmation must match | Register with a mismatched confirmation → error, no account created |
| TEST-AC-014 **[P]** | Password minimum length is 8 | Register with 7 characters → error |
| TEST-AC-015 **[P]** | Successful login creates a session | `POST /login` with valid credentials → session cookie set; `/histori` accessible |
| TEST-AC-016 **[P]** | Failed login does not reveal whether an email is registered | Same message for unknown email and wrong password |
| TEST-AC-017 **[P]** | Logout destroys the session | After logout, `/histori` → redirect to `/login`; `sessions` row deleted |
| TEST-AC-018 **[P]** | Session cookie is `HttpOnly` and `SameSite=Lax` | Inspect the `Set-Cookie` header |
| TEST-AC-019 **[P]** | Session tokens are stored hashed | DB query: `token_hash` ≠ cookie value |
| TEST-AC-020 **[P]** | Protected pages reject anonymous users | Access `/`, `/histori`, `/berita/{nid}` without a session → redirect to `/login` |
| TEST-AC-021 **[P]** | POST forms carry a CSRF token | Submit a POST without the token → 403 |
| TEST-AC-022 **[P]** | Sessions expire after the 7-day TTL | After TTL, requests → redirect to `/login`; expired row removed |

## C. Recommendation Feed

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-040 **[P]** | The feed shows at most 10 articles | `GET /` → card count = 10 (when enough exist) |
| TEST-AC-041 **[P]** | The feed comes from `/recommend`, not fabricated data | Internal request log contains `POST /recommend`; feed `nid` ⊆ API response `nid` |
| TEST-AC-042 **[P]** | Article order matches the API response order | Compare `nid` lists |
| TEST-AC-043 **[P]** | A user with history sends `history` (cold mode) | Recorded payload contains `history`; response `mode == "cold-session"` |
| ~~TEST-AC-044~~ | **Retired v1.3** — the persona/warm path was removed from the web layer | — |
| TEST-AC-045 **[P]** | The web layer never sends `user_id` and `history` together | Assert on the payload builder |
| TEST-AC-046 **[P]** | The web layer never sends `alpha` | Assert the payload has no `alpha` key |
| TEST-AC-047 **[P]** | Already-read articles do not reappear in the feed | Feed `nid` ∩ **sent** history `nid` = ∅. **Note:** if history is capped at 50 (D9), older articles outside the window can reappear — verified empirically. A mandatory second-layer web filter drops every `nid` in the user's **full** history, not just the 50 sent (see `RECOMMENDATION_INTEGRATION.md` §5.4) |
| TEST-AC-048 **[P]** | No duplicate `nid` within one feed | `len(set(nid)) == len(nid)` |
| TEST-AC-049 **[P]** | A user with no history and no topics still sees a feed | Feed shows popular articles labeled "populer" (D8) |
| TEST-AC-050 **[P]** | The feed reacts to new history | After opening one article, the `history` sent grows |
| TEST-AC-051 **[P]** | Every feed states its source | Exactly one visible label: "Berita populer" (no history) / "Rekomendasi dari riwayat bacaanmu" (cold) / "Rekomendasi berdasarkan profil dataset demo" (warm) / **"Populer di topik pilihanmu"** (v1.2: 0-view user with chosen topics) |

## D. Article Detail and Interactions

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-060 **[P]** | Detail shows title, abstract, category | `GET /berita/{nid}` → all three present in the HTML |
| TEST-AC-061 **[P]** | Detail sources data from `GET /article/{nid}` | No duplicated article text in the DB |
| TEST-AC-062 **[P]** | A displayed detail page records exactly one `view` | One `GET /berita/{nid}` for an authenticated user, rendered successfully → exactly one `interactions` row with `nid`, `user_id`, `event='view'` |
| TEST-AC-063 **[P]** | One view = one successfully displayed page load; no time-window dedupe | Two navigations to the same `nid` → exactly two rows. No user+nid dedupe window exists. Prefetch/background fetch alone → zero rows. If retries are added, they carry a unique `event_id` with an idempotency constraint so one event cannot produce two rows |
| TEST-AC-064 **[P]** | Unknown `nid` → friendly 404 page | `GET /berita/N000_nope` → 404, no stack trace |
| TEST-AC-065 **[P]** | Articles without `abstract` still render cleanly | Pick a `nid` with NULL `abstract` (5.0%) → no empty paragraph or literal "None" |
| TEST-AC-066 **[P]** | The "Berita serupa" block uses `/similar/{nid}` | Request recorded; the article itself never appears (F-08) |
| TEST-AC-067 **[P]** | No star-rating control exists anywhere | grep templates for rating widgets, `stars`, `Beri Rating` — must return nothing |

## E. History

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-070 **[P]** | The history page shows articles the user opened | `GET /histori` includes opened `nid` values |
| TEST-AC-071 **[P]** | History is ordered newest first | `created_at` descending |
| TEST-AC-072 **[P]** | History belongs only to the logged-in user | Two accounts: A's history is not visible to B |
| TEST-AC-073 **[P]** | Empty history shows a clear empty state | New account → "belum ada bacaan" message |
| TEST-AC-074 **[P]** | History is not reachable via a URL parameter | `GET /histori?user_id=2` does not show another user's history |

## F. Data Fit (anti-fabrication)

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-080 **[P]** | The UI shows no article images | No `<img>` claiming to be an article thumbnail |
| TEST-AC-081 **[P]** | The UI shows no publisher/source | No "detik.com" or any other domain presented as a source |
| TEST-AC-082 **[P]** | The UI shows no author | No "Penulis:" label with a fabricated value |
| TEST-AC-083 **[P]** | The UI shows no article publication date | No "Tanggal:" label for articles |
| TEST-AC-084 **[P]** | The UI does not render scores as percentages or stars | No `%` or progress bar derived from `score` |
| TEST-AC-085 **[P]** | Displayed categories ∈ the 18 dataset values | Assert on rendered categories |
| TEST-AC-086 **[P]** | The article count is not claimed to be 93,698 | UI copy uses the unique `nid` count or no number |

## G. Error Handling and Resilience

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-090 **[P]** | API 503 → friendly page, not a stack trace | Simulate model load failure → "system is starting" page |
| TEST-AC-091 **[P]** | API 400 on the feed → controlled fallback | Invalid payload → empty state + prompt to choose topics |
| ~~TEST-AC-092~~ | **Retired v1.3** — the web layer never sends `user_id`, so this fallback no longer exists | — |
| TEST-AC-093 **[P]** | No traceback leaks to the browser | Search for "Traceback" on every error page |
| TEST-AC-094 **[P]** | No personal data in logs | Logs contain no email or password |

## H. Performance and Operations

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-100 **[P]** | The model loads once at startup | Startup log shows a single load; no per-request load |
| TEST-AC-101 **[P]** | `GET /` (feed) responds in < 500 ms after warm-up | Measure 10 sequential requests |
| TEST-AC-102 **[P]** | `GET /berita/{nid}` responds in < 500 ms | Includes `/article` + `/similar` |
| TEST-AC-103 **[P]** | The app runs from a clean state with one command | Document the start command; the DB is created automatically |
| TEST-AC-104 **[P]** | The DB schema is created idempotently | Start twice → no "table exists" error |

## I. Code and Documentation Quality

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-110 **[P]** | `src/web/` does not import `src/models/hybrid/infer.py` | grep imports |
| TEST-AC-111 **[P]** | `src/web/` does not import evaluation modules | grep imports |
| TEST-AC-112 **[P]** | All web tests pass together with research tests | `pytest -q` green |
| TEST-AC-113 **[P]** | `docs/web/` is updated when decisions change | Review the diff |
| TEST-AC-114 **[P]** | Decisions D1–D24 have an explicit status (approved/rejected) | Decision tables are filled in |

## J. End-to-End Demo (defense evidence)

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-120 **[P]** | One demo script runs the full flow without manual `nid`/`user_id` input | Script: register→login→feed→detail→history, exit 0 |
| TEST-AC-121 **[P]** | Evidence is stored: logs + screenshots | Artifacts under `docs/evidence/web/` |
| TEST-AC-122 **[P]** | Numbers quoted during the demo match `docs/metrics_source_of_truth.md` | Cross-check |

## K. Design Compliance (`DESIGN.md`)

**ID block:** design criteria occupy `TEST-AC-201` … `TEST-AC-246`, keeping
them in the same namespace as the rest of this file while leaving room for
functional criteria in `TEST-AC-001…199`. `[P]` = MVP-mandatory.

### K.1 Token discipline

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-201 **[P]** | Every color used in CSS is a value from `DESIGN.md` `colors:` | grep the stylesheet for hex values; all must match the token list |
| TEST-AC-202 **[P]** | No new accent color is introduced | Diff of unique hex values against `DESIGN.md` |
| TEST-AC-203 **[P]** | Primary buttons use `{colors.primary}` (#181d26), never `{colors.link}` (#1b61c9) | Inspect `button-primary` background |
| TEST-AC-204 **[P]** | `{rounded.pill}` (9999px) is not used anywhere | grep `border-radius` for 9999px / `pill` |
| TEST-AC-205 **[P]** | Radii follow the scale: 6px inputs, 10px cards, 12px primary buttons | Inspect computed styles |
| TEST-AC-206 **[P]** | Spacing values are multiples of 4 and drawn from the `spacing:` scale | Inspect padding/margin values |
| TEST-AC-207 **[P]** | Content max-width ≈1280px with 48px side gutters on wide viewports | Inspect container at 1440px+ |

### K.2 Typography

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-210 **[P]** | No webfont is downloaded at runtime; no CDN `<link>` for fonts | grep templates for `fonts.googleapis`, `@font-face` with remote `src` |
| TEST-AC-211 **[P]** | Font stack is the local system stack declared in `AGENTS.md` §5.1 | Inspect `font-family` |
| TEST-AC-212 **[P]** | Display headings use weight ≤ 500 | Inspect computed `font-weight` for `h1`/`h2` |
| TEST-AC-213 **[P]** | UI chrome uses `{typography.body-md}` (14px/400/1.25); article body uses **16px/1.6** (D26) via a single `.article-body` class | Inspect computed styles; assert the tokens themselves are unchanged |
| TEST-AC-214 **[P]** | Card titles use `{typography.title-sm}` (18px/500) | Inspect `.article-card` title |

### K.3 Content integrity in the UI

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-220 **[P]** | Article cards render **no** thumbnail, `<img>`, or background image | grep templates for `<img`; inspect `background-image` |
| TEST-AC-221 **[P]** | Article cards show only `category` (and `subcategory` when present) as meta | Inspect rendered card |
| TEST-AC-222 **[P]** | No author, publication date, or publisher appears anywhere | grep rendered HTML for "Penulis", "Tanggal", "detik.com" |
| TEST-AC-223 **[P]** | `processed_text` is never rendered | grep templates for `processed_text` |
| TEST-AC-224 **[P]** | No pricing, logo-strip, or topic-rail component exists | grep templates for `pricing`, `logo-strip`, `topic-filter` |
| TEST-AC-225 **[P]** | No score is rendered in the feed or detail page | grep rendered HTML for score formatting |

### K.4 Interaction and accessibility

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-230 **[P]** | Every interactive element has a visible keyboard focus ring | Tab through each page; ring must be visible |
| TEST-AC-231 **[P]** | Focus ring color is `{colors.info-border}` (#458fff, 3.17:1) | Inspect `:focus-visible` |
| TEST-AC-232 **[P]** | Input borders are **not** `{colors.hairline}` (#dddddd, 1.36:1) | Inspect input border color; must be `muted` or `info-border` |
| TEST-AC-233 **[P]** | `{colors.border-strong}` (#9297a0, 2.93:1) is used only for disabled states | Inspect usage |
| TEST-AC-234 **[P]** | Touch targets are ≥ 44×44 px | Measure buttons and inputs |
| TEST-AC-235 **[P]** | Text contrast meets WCAG AA (≥ 4.5:1) for all rendered text pairs | Re-run the contrast table in `AGENTS.md` §5.1 |
| TEST-AC-236 **[P]** | Error text, borders, and surfaces use `{colors.signature-coral}` (#aa2d00) via `--color-error` (D25, approved 2026-10-20) | Inspect validation error styling; assert no other red hex exists |
| TEST-AC-237 **[P]** | Hover uses only the five approved token changes (D27); no transform, scale, shadow, or transition > 120 ms | Inspect `:hover` rules; grep for `transform`/`scale`/`box-shadow` |

### K.5 Layout and states

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-240 **[P]** | Breakpoints behave at < 768 / 768–1024 / 1024–1440 / > 1440 | Resize and capture screenshots |
| TEST-AC-241 **[P]** | Feed grid: 3-up desktop, 2-up tablet, 1-up mobile | Inspect at each width |
| TEST-AC-242 **[P]** | Top nav collapses to a menu below 768px | Inspect at 375px |
| TEST-AC-243 **[P]** | Loading, empty, error, and disabled states exist for feed, detail, and history | Trigger each state |
| TEST-AC-244 **[P]** | Empty state uses `{colors.signature-cream}` with dark ink text | Inspect |
| TEST-AC-245 **[P]** | Hard error page uses `{colors.signature-coral}` with white text and a retry action | Inspect 503 page |
| TEST-AC-246 **[P]** | No `<img>` placeholder or generated graphic stands in for missing article images | grep templates |

### K.6 Persona picker and reader counts (added 2026-10-21)

| ID | Criterion | Verification |
|----|-----------|--------------|
| TEST-AC-250 **[P]** | `/login/persona` returns 404 unconditionally (v1.3: the feature is deleted, not gated) | `test_auth.py::test_persona_endpoints_are_gone` (cites TEST-AC-250) |
| ~~TEST-AC-251~~ | **Retired v1.3** — there is no picker to list users | — |
| ~~TEST-AC-252~~ | **Retired v1.3** — the picker POST endpoint is gone; the surviving invariant (404) is TEST-AC-250 | — |
| ~~TEST-AC-253~~ | **Retired v1.3** — there is no picker and no warm path | — |
| TEST-AC-254 **[P]** | Cards show a dataset reader count and an app reader count, both unique per user | Open one article 3× from one account; the app count must rise by 1 |
| TEST-AC-255 **[P]** | A zero reader count is never printed; the row renders nothing instead | Grep the rendered feed for `>0× via MIND<` and `>0× via web<` |
| TEST-AC-256 **[P]** | Reader counts are labelled by source, so a dataset sample is never presented as total readership | Inspect card and history copy for `× via MIND` and `× via web` |
| TEST-AC-257 **[P]** | A history row keeps its column geometry whether it carries one count or both | Measure `.history-cat`, `.history-time`, `.history-readers` left edges across rows; all rows must agree |
| TEST-AC-258 **[P]** | Reader counts are visually subordinate to the title and abstract | Computed opacity of `.card-readers` and `.history-readers` is below 1 |

---

## L. Corpus transition addendum (2026-10-27 — EFFECTIVE, PRD v1.1 disetujui)

Kriteria §A–K ditulis terhadap implementasi era MIND yang berjalan hari ini dan
tetap benar sampai migrasi fase-2 dieksekusi. Setelah korpus aktif berganti
(PRD v1.1), delta berikut berlaku — dicatat lebih dulu supaya migrasi tidak
bisa lolos tanpa jejak:

| Menyentuh | Kriteria fase-2 | Catatan |
|-----------|-----------------|---------|
| TEST-AC-060 | Detail menampilkan judul, kategori, sumber, tanggal terbit, dan konten penuh | Tidak ada `abstract`/`subcategory` di katalog aktif |
| TEST-AC-065 | Artikel dengan konten kosong/pendek tetap render bersih | 0,01% kosong (terukur); boilerplate distrip di pipeline penelitian |
| TEST-AC-081 | UI **boleh** menampilkan label sumber nyata (kompas/tempo/detik) sebagai teks; tautan portal tetap dilarang | Membalik 081 |
| TEST-AC-083 | UI **boleh** menampilkan tanggal terbit artikel yang nyata | Membalik 083 |
| TEST-AC-085 | Kategori tampil ∈ hasil pemetaan seksi URL yang terdokumentasi di lock aktif | Mengganti 18 nilai MIND |
| TEST-AC-086 | Jangan klaim jumlah artikel apa pun secara hardcoded; angka mengikuti `data/DATASET_LOCK_INDO.md` | Digeneralisasi |
| TEST-AC-221 | Meta kartu = kategori + sumber + tanggal | `subcategory` tidak ada lagi |
| TEST-AC-222 | Tanpa penulis dan tanpa tautan portal; label "Sumber:" dan "Tanggal:" justru WAJIB tampil bila ada nilainya | Sebagian dibalik |
| TEST-AC-255/256 | Label reader-count sumber dataset `× via MIND` → sumber baru dihitung dari interaksi simulasi korpus aktif; aturan zero-count (D30) tetap | D29 berlanjut dengan data simulasi |
| TEST-AC-049 | Feed populer bersumber dari statistik interaksi train hasil simulasi | Label "Berita populer" tidak berubah |

**Status pelaksanaan (2026-10-27):** PRD v1.1 disetujui dan
`data/DATASET_LOCK_INDO.md` sudah lepas dari status TBC, sehingga seluruh
baris di atas **efektif**. Implementasinya terpetakan sebagai berikut:

| Kriteria | Test yang menjalankannya |
|---|---|
| TEST-AC-060 | `tests/web/test_addendum_l_indo_ui.py::test_detail_shows_full_content_source_and_date` |
| TEST-AC-065 | `…::test_short_or_empty_content_renders_cleanly` |
| TEST-AC-081 | `…::test_rendered_source_matches_catalog` + `test_no_fabricated_metadata_anywhere` |
| TEST-AC-083 | `…::test_rendered_date_matches_catalog` |
| TEST-AC-085 | `…::test_rendered_categories_are_served_catalog_values` |
| TEST-AC-086 | `…::test_no_hardcoded_article_count_anywhere` |
| TEST-AC-221 | `…::test_card_meta_is_category_source_and_date_only` + `test_cards_show_category_source_and_date` |
| TEST-AC-222 | `…::test_no_author_no_portal_link_but_source_and_date_labelled` |
| TEST-AC-255/256 | `test_traceability.py::test_zero_reader_counts_are_hidden` / `…::test_cards_show_unique_reader_counts` (label era-aware: `× via simulasi` untuk korpus indo, `× via MIND` untuk era MIND) |
| TEST-AC-257 | `tests/web/test_addendum_l_indo_ui.py::test_history_row_keeps_four_grid_cells` |

**Kriteria yang dibalik/diamendemen (bukan sekadar ditambah):** baris §A–K
`TEST-AC-081`, `TEST-AC-083`, `TEST-AC-221`, `TEST-AC-222` semula melarang
sumber dan tanggal; addendum ini membalik keduanya menjadi **wajib bila
korpus memilikinya**. `TEST-AC-051` (tiga label feed) tidak berubah karena
addendum pilih-topik (PRD v1.2) belum disetujui.

---

## M. Topic onboarding for 0-view users (2026-10-27, PRD v1.2)

Scope: `PRD_Addendum_v1.2_Pilih_Topik_Cold_Start.md` §7 (`PRD-AC-55…62`).
Numbering continues at **259** — 123–258 are already used (demo 120–122,
MIND-era UI 123+, corpus-transition §L 250–258).

| ID | Criterion | How it is checked |
|----|-----------|-------------------|
| TEST-AC-259 **[P]** | The topic feed renders only for a user with zero `view` events; users with history never receive it | `test_topics.py::test_topic_feed_renders_for_zero_view_user_only` — label present before the first view, absent after |
| TEST-AC-260 **[P]** | Every topic-feed card belongs to a chosen topic, or comes from the global top-up when a topic pool runs dry | `…::test_topic_feed_categories_match_choice_or_global_topup` plus `data/DATASET_LOCK_INDO.md` §Topik pool numbers |
| TEST-AC-261 **[P]** | The topic feed adds no `POST /recommend` call and never sends or changes α | `…::test_topic_feed_never_calls_recommend` — a spy asserts zero payloads |
| TEST-AC-262 **[P]** | Two users with the same topic set get an identical order (determinism from canonical `position` + round-robin) | `…::test_topic_order_is_deterministic_across_users` — same chips submitted in different form order |
| TEST-AC-263 **[P]** | Chips are exactly the 12 measured labels; `Pemilu`, `Ramadan`, `Otomotif`, `Investigasi`, `Bersponsor`, `Berita`, `Info Tempo` and raw portal tags never appear | `…::test_chip_set_is_the_measured_twelve` |
| TEST-AC-264 **[P]** | The form accepts at most 3 chips, rejects labels outside the set, requires CSRF, and is skippable without side effects | `…::test_onboarding_rejects_unknown_label_and_too_many`, `…::test_onboarding_requires_csrf`, `…::test_onboarding_offered_once_then_never_again`, `…::test_empty_submission_is_a_skip` |
| TEST-AC-265 **[P]** | `user_topics` is written only by `src/web/`; the research pipeline never reads it; zero chips means "no preference" | `…::test_topics_are_profile_data_not_events` + `test_units.py::test_schema_init_is_idempotent` |
| TEST-AC-266 **[P]** | The new-user smoke flow covers register → (optional) topics → labelled topic feed → detail → `view` → history path | `…::test_smoke_flow_register_topic_detail_history` + `scripts/smoke_web.sh` scenario 3b |

**Onboarding shown exactly once** (PRD-AC-55 / C2) is enforced by
`users.topics_prompted_at`, not by the absence of `user_topics` rows: a user
who presses "Lewati" stores no preference, so zero rows cannot distinguish
"skipped" from "never asked". `Store.init_schema` adds the column through an
idempotent `PRAGMA table_info`-guarded `ALTER TABLE`, because
`CREATE TABLE IF NOT EXISTS` does nothing to an existing `users` table.

---

## N. Web polish + persona removal (2026-10-27, v1.3)

| ID | Criterion | How it is checked |
|----|-----------|-------------------|
| TEST-AC-267 **[P]** | On the topic onboarding screen the wordmark is not a link (navigation locked), and both "Simpan pilihan" and "Lewati" are present | `test_topics.py::test_onboarding_locks_navigation` (cites TEST-AC-267) |
| TEST-AC-268 **[P]** | Article bodies never start with the leftover dateline comma; the corpus itself is unchanged | `test_addendum_l_indo_ui.py::test_body_starts_without_dateline_comma` + `test_textview.py` unit cases (cite TEST-AC-268) |
| TEST-AC-269 **[P]** | `.article-body` is justified with a first-line indent, using tokens only | `…::test_article_body_is_justified` (cites TEST-AC-269) |
| TEST-AC-270 **[P]** | History rows share one height and identical column offsets, whatever the title/date length | `test_addendum_l_indo_ui.py::test_history_row_keeps_four_grid_cells`, `…::test_history_rows_share_one_height` (cites TEST-AC-270) + browser measurement |
| TEST-AC-271 **[P]** | No persona feature remains: `/login/persona` 404s, the login page does not advertise it, and `Config`/`Store` carry no persona surface | `test_auth.py::test_persona_endpoints_are_gone`, `…::test_config_has_no_persona_fields` (cite TEST-AC-271) |
| TEST-AC-272 **[P]** | The feed renders at most 12 unique cards | `test_feed.py::test_feed_never_exceeds_twelve` (cites TEST-AC-272) |
| TEST-AC-273 **[P]** | The detail page shows exactly one portal link, after the body, whose host matches the article's `source` | `test_addendum_l_indo_ui.py::test_no_author_and_source_link_only_from_data` (cites TEST-AC-273) |
| TEST-AC-274 **[P]** | Up to 5 topics are accepted and the topic feed then renders 12 cards (`q = ceil(12/5) = 3`) | `test_topics.py::test_five_topics_accepted_and_feed_has_twelve_cards` (cites TEST-AC-274) |
| TEST-AC-275 **[P]** | The onboarding heading carries no number, while the 5-chip cap is enforced server-side | `…::test_onboarding_label_has_no_number`, `…::test_onboarding_rejects_unknown_label_and_too_many` (cite TEST-AC-275) |

---

## Traceability

Every criterion above is cited by at least one test. Coverage is mechanical,
not asserted:

| Measure | Value |
|---------|-------|
| Criteria (`TEST-AC-NNN`) | 125 |
| Cited by a test | **125** |
| Test functions in `tests/web/` | 196 (7 of 12 files cite criteria; the rest are behavioural guards) |

Note (v1.3): deleting the persona feature retired TEST-AC-251/252/253 rather
than leaving them "covered" by tests that no longer exist, and the count is
**not** held at a previous number on purpose — it is whatever the snippet
prints. Deleting tests that guard a deleted feature is correct; padding the
suite to preserve a number would not be.

Numbers are produced by the snippet below, not typed by hand — re-run it after
adding a criterion or a test instead of editing this table.

Verify:

```bash
python - <<'EOF'
import re, pathlib
doc = pathlib.Path('docs/web/ACCEPTANCE_CRITERIA.md').read_text()
criteria = set(re.findall(r'^\|\s*(TEST-AC-\d+)\s*\*\*\[[PS]\]\*\*', doc, re.M))
cited = set()
for p in pathlib.Path('tests/web').glob('*.py'):
    cited |= set(re.findall(r'TEST-AC-\d+', p.read_text()))
print(f"{len(criteria - cited)} uncited of {len(criteria)}")
EOF
```

Criteria belonging to CI or the demo script are covered in
`tests/web/test_traceability.py`, which inspects those artefacts directly
(`scripts/ci/*.py`, `scripts/smoke_web.sh`, `docs/evidence/web/`, `docs/web/*.md`)
rather than duplicating their logic.

---

## Summary for Approval

**Namespace reminder:** `TEST-AC-xxx` (this file) vs `PRD-AC-xx`
(`PRD_Web_Rekomendasi_Berita.md` §14). They are separate on purpose.

- **MVP mandatory [P]:** TEST-AC-001…008, 010…021, 040…050, 060…066,
  070…074, 080…086, 090…094, 100…104, 110…114, 120…122.
- **Design mandatory [P]:** TEST-AC-201…207, 210…214, 220…225, 230…237,
  240…246, 250…258 (42 criteria).
- **Next stage [S]:** none. Session TTL and the feed source label were raised
  to **[P]**; the rating criteria were removed (ratings are out of MVP).

**Superseded (2026-10-27):** the six topic-onboarding criteria previously
`AC-30…AC-35` were removed when topic selection was out of MVP scope. PRD v1.2
reintroduces a **narrowly scoped** topic feature (0-view users only, optional,
once, candidate selection only), specified by `PRD-AC-55…62` and tested as
`TEST-AC-259…266`; the old `AC-30…AC-35` ids stay retired and must never be
reused. Original note for the record: topic selection was out of MVP scope per `PRD_Web_Rekomendasi_Berita.md`
§5.2 and §18. Registration now redirects to `/` (the feed).

### Decisions recorded 2026-10-20

| ID | Decision | Status |
|----|----------|--------|
| D13 | Add a narrow `load_recommender()` seam in `src/api/main.py` (option B) — no endpoint, schema, algorithm, artifact, or α change; proven by the existing contract test, full research test suite, and freeze audit | ✅ Approved |
| D14 | One process — web app mounts the frozen API | ✅ Approved |
| D15 | SQLite | ✅ Approved |
| D16 | Web app does not expose `/docs` | ✅ Approved |
| D17 | Keep all interactions, no purge | ✅ Approved |
| D18 | Keep the `source` column | ✅ Approved |
| D21 | Do not add a response field for the content-only fallback (option a) | ✅ Approved |
| D22 | No score shown anywhere in the UI; no debug page in MVP scope | ✅ Approved |
| D23/D19 | History: 50 unique `nid`, then filter against the full history | ✅ Approved |
| D24 | `/similar` only on the detail page | ✅ Approved |
| D25 | `{colors.signature-coral}` (#aa2d00) as `--color-error` | ✅ Approved |
| D26 | Article body 16px/1.6 via `.article-body` | ✅ Approved |
| D27 | Hover restricted to five token-only changes, ≤ 120 ms | ✅ Approved |
| — | Session TTL: **7 days** | ✅ Approved |
| — | ~~Demo persona via `WEB_DEMO_PERSONA_USER_ID`~~ — **revoked v1.3** (feature removed) | ❌ Revoked |
| — | Star ratings: **out of MVP** | ✅ Approved |
| — | Feed source label: **in MVP**, raised to priority P | ✅ Approved |

### Decisions recorded 2026-10-21

| ID | Decision | Status |
|----|----------|--------|
| D28 | ~~Passwordless persona picker at `/login/persona`~~ — **revoked v1.3**: picker, seed CLI, column and warm path all removed; the app has no roles | ❌ Revoked |
| D29 | Reader counts shown on cards come from two labelled sources: dataset unique readers (MIND sample) and app unique readers (this deployment). Both count unique users, not views | ✅ Approved |
| D30 | A zero reader count is hidden rather than printed. Only 13.9% of catalogue nids appear in the interactions at all, so "0 pembaca" would assert something the data cannot support | ✅ Approved |

Consequence of D22: score-bearing criteria are **deleted**, not deferred. No
`TEST-AC` requires a debug page, and none requires a score to be rendered.
Development-time score checks happen through tests and internal tooling.

**No open questions remain in this document.** Anything still undecided lives in
`PRD_Web_Rekomendasi_Berita.md` or in `ARCHITECTURE.md` §12.
