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
| TEST-AC-010 **[P]** | Users can register with name, email, password | Register form POST → 303 redirect to **`/`** (feed); one `users` row added |
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
| TEST-AC-044 **[P]** | A persona account sends `user_id` (warm mode) | Payload contains `user_id`; response `mode == "warm"` |
| TEST-AC-045 **[P]** | The web layer never sends `user_id` and `history` together | Assert on the payload builder |
| TEST-AC-046 **[P]** | The web layer never sends `alpha` | Assert the payload has no `alpha` key |
| TEST-AC-047 **[P]** | Already-read articles do not reappear in the feed | Feed `nid` ∩ **sent** history `nid` = ∅. **Note:** if history is capped at 50 (D9), older articles outside the window can reappear — verified empirically. A mandatory second-layer web filter drops every `nid` in the user's **full** history, not just the 50 sent (see `RECOMMENDATION_INTEGRATION.md` §5.4) |
| TEST-AC-048 **[P]** | No duplicate `nid` within one feed | `len(set(nid)) == len(nid)` |
| TEST-AC-049 **[P]** | A user with no history and no topics still sees a feed | Feed shows popular articles labeled "populer" (D8) |
| TEST-AC-050 **[P]** | The feed reacts to new history | After opening one article, the `history` sent grows |
| TEST-AC-051 **[P]** | Every feed states its source | Exactly one visible label: "Berita populer" (no history) / "Rekomendasi dari riwayat bacaanmu" (cold) / "Rekomendasi berdasarkan profil dataset demo" (warm) |

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
| TEST-AC-092 **[P]** | API 404 on `user_id` → fall back to `history` | Invalid persona → feed still renders via history |
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
| TEST-AC-250 **[P]** | `/login/persona` returns 404 and the login page hides its link unless `WEB_PERSONA_PICKER` is set | Request the route with the flag off; grep `/login` for the link |
| TEST-AC-251 **[P]** | The picker lists only `user_id`s present in the ALS `user_map` | Compare rendered ids against `recommender_data["user_map"]` |
| TEST-AC-252 **[P]** | The picker POST rejects any id outside `user_map` with 400, and still enforces CSRF (403) | Post unknown ids, empty string, and an injection-shaped string |
| TEST-AC-253 **[P]** | Picker login creates one account per persona, idempotently, and lands on the warm path | Log in twice with the same persona; assert a single row and `mode == "warm"` |
| TEST-AC-254 **[P]** | Cards show a dataset reader count and an app reader count, both unique per user | Open one article 3× from one account; the app count must rise by 1 |
| TEST-AC-255 **[P]** | A zero reader count is never printed; the row renders nothing instead | Grep the rendered feed for `>0× via MIND<` and `>0× via web<` |
| TEST-AC-256 **[P]** | Reader counts are labelled by source, so a dataset sample is never presented as total readership | Inspect card and history copy for `× via MIND` and `× via web` |
| TEST-AC-257 **[P]** | A history row keeps its column geometry whether it carries one count or both | Measure `.history-cat`, `.history-time`, `.history-readers` left edges across rows; all rows must agree |
| TEST-AC-258 **[P]** | Reader counts are visually subordinate to the title and abstract | Computed opacity of `.card-readers` and `.history-readers` is below 1 |

---

## L. Corpus transition addendum (2026-10-27 — DRAFT, PRD v1.1)

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

Tidak ada satu pun baris di addendum ini yang efektif sebelum PRD v1.1
disetujui dan `data/DATASET_LOCK_INDO.md` lepas dari status TBC.

---

## Traceability

Every criterion above is cited by at least one test. Coverage is mechanical,
not asserted:

| Measure | Value |
|---------|-------|
| Criteria (`TEST-AC-NNN`) | 111 |
| Cited by a test | **111** |
| Test functions in `tests/web/` | 163 (5 of 9 files cite criteria; the rest are behavioural guards) |

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

**Removed:** the six topic-onboarding criteria (previously `AC-30…AC-35`). Topic selection is out of MVP scope per `PRD_Web_Rekomendasi_Berita.md`
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
| — | Demo persona via `WEB_DEMO_PERSONA_USER_ID`, seeded by an explicit idempotent command | ✅ Approved |
| — | Star ratings: **out of MVP** | ✅ Approved |
| — | Feed source label: **in MVP**, raised to priority P | ✅ Approved |

### Decisions recorded 2026-10-21

| ID | Decision | Status |
|----|----------|--------|
| D28 | Passwordless persona picker at `/login/persona`, gated by `WEB_PERSONA_PICKER` (default **off**). The page is the credential: anyone who loads it enters any listed demo account, so it must not be enabled on a public deployment. Amends D4 from "one demo account" to "one account per chosen dataset user, created on demand" | ✅ Approved |
| D29 | Reader counts shown on cards come from two labelled sources: dataset unique readers (MIND sample) and app unique readers (this deployment). Both count unique users, not views | ✅ Approved |
| D30 | A zero reader count is hidden rather than printed. Only 13.9% of catalogue nids appear in the interactions at all, so "0 pembaca" would assert something the data cannot support | ✅ Approved |

Consequence of D22: score-bearing criteria are **deleted**, not deferred. No
`TEST-AC` requires a debug page, and none requires a score to be rendered.
Development-time score checks happen through tests and internal tooling.

**No open questions remain in this document.** Anything still undecided lives in
`PRD_Web_Rekomendasi_Berita.md` or in `ARCHITECTURE.md` §12.
