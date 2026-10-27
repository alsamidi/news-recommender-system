# AGENTS.md — Working Rules for Agents in This Repository

This document is the rulebook for agents (human or AI) working in
`alsamidi/news-recommender-system`. It states **what is frozen**, **what may be
changed**, and **how to verify** changes.

Product/technical documents for the web layer live in `docs/web/` (start with
`docs/web/PRD.md`). Those documents are **not yet approved**; read their
"Decisions Awaiting Approval" sections before acting on them.

---

## 1. Context

An Indonesian-language news recommendation system for a thesis (Tugas Akhir):

- Content-based **TF-IDF** + **implicit ALS** collaborative filtering + **weighted hybrid**.
- MINDsmall / xMINDsmall datasets (English + Indonesian translation), file-based temporal split.
- **Fase 2 (2026-10-27, PRD v1.1):** korpus aktif berganti ke korpus portal
  Indonesia (Detik/Tempo/Kompas; Juli 2024 – Oktober 2025; 80.472 baris mentah →
  67.381 unik) dengan interaksi simulasi akun dummy (`view` saja) —
  `data/DATASET_LOCK_INDO.md` + `docs/web/PRD_Web_Rekomendasi_Berita.md` v1.1.
  Riset v1 (MIND) tetap beku; angkanya tetap sumber kebenaran untuk dokumen lama.
- Serving layer: FastAPI + `HybridRecommender` over frozen artifacts.
- The web application layer (auth, feed, history, profile) **sudah diimplementasikan
  dan melebur ke `develop`** (PRD v1.0; lihat §6.4 koreksi status; **PRD v1.1
  disetujui 2026-10-27** dan sudah diimplementasikan di `feat/dataset-indo-news`).

## 2. Repository Map

| Path | Contents | Status |
|------|----------|--------|
| `README.md` | Research summary, results, reproduction steps | Frozen (facts) |
| `data/DATASET_LOCK.md` | Official dataset pairs + sha256 + split rules | **Frozen** |
| `data/DATASET_LOCK_INDO.md` | Phase-2 aktif: korpus portal Indonesia + interaksi simulasi; hash, skema katalog turunan, aturan split | **Terkunci 2026-10-27** (Gate A/B/C + split + evaluasi + serving) |
| `docs/API_CONTRACT.md` | API contract v1.0.0 | **Frozen** |
| `docs/openapi.json` | OpenAPI snapshot v1.0.0 | **Frozen** (regenerate only on version bump) |
| `docs/RESEARCH_FREEZE.md` | P3.4 freeze audit | **Frozen** |
| `docs/metrics_source_of_truth.md` | Report number → source JSON map | **Frozen** |
| `configs/*.yaml` | Model and preprocessing configuration | **Frozen** |
| `src/preprocessing/`, `src/models/`, `src/evaluation/` | Research pipelines | **Frozen** |
| `src/api/main.py` | Serving API v1.0.0 | **Frozen** (bug fixes only) |
| `src/models/hybrid/infer.py` | Full-catalog inference | **Frozen** (bug fixes only) |
| `src/api/templates/demo.html` | P3.2 demo viewer | Frozen, outside the API contract |
| `tests/` | 26 tests (parity, API, demo) | May be added to; never weakened |
| `docs/web/PRD_Web_Rekomendasi_Berita.md` | **Authoritative PRD** (scope, behavior, locked decisions) | Editable with approval |
| `docs/web/DESIGN.md` | Visual design tokens (colors, type, spacing, radii, components) | **Reference — do not rewrite** |
| `docs/web/Diagram_Desain_Web_Rekomendasi_Berita.md` | Conceptual diagrams (use case, activity, class, ERD) | Reference |
| `docs/web/ARCHITECTURE.md` | Technical architecture, integration decisions | Editable |
| `docs/web/ACCEPTANCE_CRITERIA.md` | Testable acceptance criteria | Editable |
| `docs/web/UX_FLOWS.md` | Screen flows and Figma ↔ data fit | Editable |
| `docs/web/DATA_MODEL.md` | SQLite schema for the web layer | Editable |
| `docs/web/RECOMMENDATION_INTEGRATION.md` | Web ↔ frozen-model integration rules | Editable |
| `docs/web/PRD.md` | Earlier PRD draft — **SUPERSEDED**, archived | Never use as scope source |
| `.env.example` | Documented local environment variables (no secrets) | Committed; `.env` is ignored |

Raw datasets (`MINDsmall_*`, `xMINDsmall_*`) and large artifacts
(`models/*.pkl`, `*.npy`, `*.npz`) are **not committed** (see `.gitignore`).
File korpus aktif `data/raw/final_merge_dataset.csv` (216,4 MB) juga tidak
dikomit — hash dan profilnya tercatat di `data/DATASET_LOCK_INDO.md`.

## 3. Hard Rules

### 3.1 Do not touch what is frozen

1. **Never retrain models.** The artifacts under `models/` are records of
   completed research. ALS is not bit-deterministic across runs, so retraining
   changes the numbers in the report.
2. **Never re-run evaluation pipelines** (`src/evaluation/*`) as a side effect of
   a probe. Pipelines may be read, not executed.
3. **Never change frozen numbers** in README, `docs/metrics_source_of_truth.md`,
   or `models/*_tables.md`. The authoritative numbers live in `models/*_eval.json`.
4. **Never mix splits.** Train only from `*_train`, evaluate only on `*_dev`,
   cutoff `2019-11-15`. Random splits are forbidden (leakage).
5. **Never refit the vectorizer.** TF-IDF is `transform()`-only on the full catalog.
6. **Never change α.** The serving value `0.4` comes from `configs/hybrid.yaml`
   and is guarded by `test_serving_alpha_matches_table_b_winner`. There is no
   per-request override. (Era MIND. Untuk korpus fase 2, nilai α ditetapkan
   di konfigurasi penelitian korpus baru melalui grid kecil yang terdokumentasi
   — `src/web/` tetap tidak pernah mengirim atau mengubah α.)
7. **Never add or change contract routes** (`/health`, `/recommend`,
   `/similar/{nid}`, `/article/{nid}`) without a version bump, a regenerated
   `docs/openapi.json`, and fresh parity/smoke evidence.

### 3.2 Do not be academically misleading

- Do not write "accuracy" for NDCG/MAP. Low absolute scores (NDCG@10 ≈ 0.002)
  are a property of the task, not a bug — explain them with the 93,698-row
  catalog context.
- Do not claim cold-start numbers apply to all sessions: the valid claim covers
  only the subset that has ALS items (n=1,164 out of 2,000).
- Do not compare Table D rows with different `n` without naming the `n` column.
- Do not claim star ratings influence the model. The frozen model uses only
  implicit interactions from the dataset.

### 3.3 Data and privacy

- Never commit credentials, `.env` files, real password hashes, or user data.
- Dataset `user_id` values (e.g. `U10022`) are demo personas, not real accounts.

## 4. Expected Workflow

```bash
source venv/bin/activate          # Python 3.12, venv at repo root
python -m pytest -q               # baseline: 26 passed
bash scripts/audit_freeze.sh      # freeze audit (safe, probes only)
bash scripts/smoke_demo.sh        # end-to-end API + demo UI proof
```

Before declaring work finished:

1. `python -m pytest -q` is green (never reduce the test count).
2. `bash scripts/audit_freeze.sh` still prints `RESEARCH FREEZE AUDIT PASSED`.
3. `git status` contains only the intended changes.
4. If you touched any document containing numbers, re-run the audit.

### Probe rule

Probes must be **side-effect free**. Never call
`python -m src.preprocessing.build_locked` without `--help`: the original
`main()` launched a full multiprocessing rebuild (incident recorded in
`docs/RESEARCH_FREEZE.md`).

## 5. Code Conventions

- Python 3.12, `src/` on `sys.path` (see `tests/conftest.py`).
- Code docstrings and comments: English. Documentation: English. UI strings:
  Indonesian, matching the PRD §16 copy.
- Existing style: short functions, explicit asserts for invariants, no extra
  frameworks when the standard library suffices.
- The new web layer **must not** import the evaluation pipelines for serving
  purposes; `HybridRecommender` is the only scoring path.

## 5.1 Design System (DESIGN.md)

`docs/web/DESIGN.md` is the **single source of truth for visual decisions**:
color, typography, spacing, radii, and component styling. Do not invent new
colors, sizes, or radii — reference the token.

### Precedence when documents disagree

1. **Data availability** (what the catalog actually contains) — non-negotiable.
2. **API contract v1.0.0** and `PRD_Web_Rekomendasi_Berita.md` §18 locked
   decisions — scope and behavior.
3. **`DESIGN.md`** — appearance only.
4. Older drafts (`PRD.md`) — ignored.

`DESIGN.md` is an analysis of Airtable's **marketing site**. It is a *style*
reference, not a product spec. Where it assumes content we do not have, or
components outside our scope, the lower-precedence item loses. The known
collisions are listed in §6.1.

### Tokens in use

| Area | Rule |
|------|------|
| Color | Only values from `colors:` in the DESIGN.md front matter. Primary action = `{colors.primary}` (#181d26), **not** `{colors.link}` (#1b61c9). |
| Type | `{typography.body-md}` (14/400) for body, `{typography.title-sm}` (18/500) for card titles, `{typography.display-md}`/`display-lg` for page headings, `{typography.button}` for buttons. Never bolder than 500 in display sizes. |
| Spacing | 4px base unit; use the `spacing:` scale. `{spacing.section}` (96px) is for marketing-style bands only — app screens use `{spacing.xl}`/`{spacing.xxl}`. |
| Radius | `{rounded.sm}` (6px) inputs, `{rounded.md}` (10px) cards, `{rounded.lg}` (12px) primary buttons and signature cards, `{rounded.full}` icon buttons. **`{rounded.pill}` is pricing-only — do not use it.** |
| Layout | Max content width ~1280px, `{spacing.xxl}` (48px) side gutters, breakpoints < 768 / 768–1024 / 1024–1440 / > 1440. |
| Touch targets | ≥ 44×44 px (DESIGN.md specifies 48px for buttons, 44px for inputs). |

### Fonts — required substitution

`DESIGN.md` specifies **Haas Groot Disp** and **Haas Grotesk**, which are
commercially licensed and **not available** in this project. Do not add a CDN
font (PRD §12 forbids runtime CDN dependencies for core CSS/JS).

Use a local system stack only:

```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
             "Helvetica Neue", Arial, sans-serif;
```

`DESIGN.md` itself endorses `system-ui` as sufficient on macOS/iOS. Accept the
resulting metric difference; do not fake Haas with a webfont download.

### Article body typography — decided 2026-10-20

`DESIGN.md` sets body copy at **14px / 400 / 1.25** (`{typography.body-md}`),
tuned for marketing copy rather than sustained reading.

**Decision D26 (APPROVED 2026-10-20):** article body text renders at **16px /
1.6**. Everything else stays at the token value.

| Context | Size | Line height | Source |
|---------|------|-------------|--------|
| Article body (`abstract` on detail page) | 16px | 1.6 | Local override, D26 |
| All UI chrome (nav, meta, buttons, forms) | 14px | 1.25 | `{typography.body-md}` |
| Card titles | 18px | 1.4 | `{typography.title-sm}` |
| Page headings | 32–40px | 1.2 | `{typography.display-md}` / `display-lg` |

Rules:
- The override is applied by a **single CSS class** (`.article-body`) in
  `app.css`. Do not change the `--type-body-*` tokens themselves.
- Measure article text at **65–75 characters** per line.
- Do not enlarge headings to compensate; keep the token scale.

### Interaction states — deliberate deviation

`DESIGN.md` documents **no hover states** (an extraction artifact of the
marketing site) and only a focus state for `text-input`.

For an authenticated web app this is insufficient. Required exceptions:

- **Keyboard focus is mandatory** on every interactive element: visible ring
  using `{colors.info-border}` (#458fff, 3.17:1 on white — meets WCAG 1.4.11).
- **Hover may be used** for affordance, restricted to the token-only changes
  approved in D27 below.
- **No motion/transition** beyond simple opacity or background changes.

### Accessibility constraints discovered by measurement

Contrast ratios computed against `#ffffff` (WCAG 2.1):

| Token | Ratio | Verdict |
|-------|-------|---------|
| `ink` #181d26 | 16.90:1 | AAA |
| `body` #333840 | 11.79:1 | AAA |
| `muted` #41454d | 9.62:1 | AAA |
| `link` #1b61c9 | 5.83:1 | AA |
| `on-primary` on `signature-coral` | 6.81:1 | AA |
| `on-primary` on `signature-forest` | 14.89:1 | AAA |
| `hairline` #dddddd (border) | **1.36:1** | **Fails 3:1 non-text** |
| `border-strong` #9297a0 (border) | **2.93:1** | **Fails 3:1 non-text** |

Consequences:

- **Never use `{colors.hairline}` as the only boundary of an input or control.**
  It is a divider color. Input borders must be `{colors.muted}` (#41454d) or
  `{colors.info-border}` (#458fff) to satisfy WCAG 1.4.11.
- `{colors.border-strong}` is 2.93:1 — acceptable only for disabled states
  where the control is intentionally non-operable.

### Missing tokens — decided 2026-10-20

`DESIGN.md` has **no error/danger color**. It provides `info` and `success`
only, and its "Known Gaps" admits form validation states were never extracted.
The app needs error states (validation, 404, 503).

**Decision D25 (APPROVED 2026-10-20):** use `{colors.signature-coral}`
(#aa2d00) as the error color.

| Use | Value | Contrast |
|-----|-------|----------|
| Error surface background | `{colors.signature-coral}` with `{colors.on-primary}` text | 6.81:1 |
| Error text on canvas | `{colors.signature-coral}` | 6.81:1 |
| Error input border | `{colors.signature-coral}` (1px) | 6.81:1 vs white |

Do **not** introduce a new red hex. Do not add a `danger` token to
`DESIGN.md`; the alias lives in `tokens.css` as `--color-error:
var(--color-signature-coral)`.

**Why not `{colors.info}`:** info-blue reads as advisory, not as failure.
**Why not `{colors.success}`:** obviously wrong semantic.

### Interaction states — decided 2026-10-20

**Decision D27 (APPROVED 2026-10-20):** hover states are permitted, restricted
to token colors.

Permitted hover changes only:

| Element | Allowed change |
|---------|----------------|
| Article card | background `{colors.canvas}` → `{colors.surface-soft}` |
| Text link | color `{colors.link}` → `{colors.link-active}` |
| Primary button | background `{colors.primary}` → `{colors.primary-active}` |
| Secondary button | background `{colors.canvas}` → `{colors.surface-soft}` |
| Nav item | color `{colors.ink}` → `{colors.muted}` |

Not permitted: transforms, scale, translate, box-shadow additions, color
values outside the token set, or any transition longer than 120 ms.

Focus states remain **mandatory and independent of hover** (TEST-AC-230/231): a
keyboard user must see the ring without hovering.

### Out-of-scope design components

Do **not** implement these from `DESIGN.md`:

| Component | Why not |
|-----------|---------|
| `pricing-*`, `button-pricing-pill` | No pricing surface in this product |
| `logo-strip` | No partner logos |
| `topic-filter-rail` | Topic selection is out of MVP scope (PRD §5.2) |
| `hero-band` rainbow-stripe treatment | Marketing artifact; not a news-app pattern |
| `demo-grid-card` grids | Marketing artifact |

`article-card` **is** in scope, but see the thumbnail rule in §6.1.



## 6. Known Traps

### 6.1 Design ↔ Data collisions (DESIGN.md vs. reality)

`DESIGN.md` was extracted from Airtable's marketing site. These components
assume content we do not have. **Data availability wins** (PRD §10.3).

| DESIGN.md says | Reality | Resolution |
|----------------|---------|------------|
| `article-card` carries a **16:9 illustrated thumbnail** | Catalog has no image column (F-16) | Render the card **without** a thumbnail. Do not substitute a placeholder image, stock photo, or generated graphic. If a visual anchor is needed, use a flat token-colored bar (e.g. `{colors.surface-soft}`) with no imagery. |
| `article-card` carries a **meta line** (author/date/source) | MIND: tidak ada satu pun (F-16). Korpus aktif: punya `source` dan tanggal terbit nyata (bukan author), tetap tanpa gambar | Korpus aktif: tampilkan `category` + `source` + tanggal (PRD v1.1 §10.2); author/subkategori tetap jangan |
| `article-card` has a **small uppercase category tag** | `category` exists (18 values) | ✅ Use it. This is the one meta element that is real. |
| `topic-filter-rail` (240px left rail) | Topic selection is out of MVP (PRD §5.2) | Do not build it. No category filtering in the MVP. |
| `hero-band` with 96px padding and rainbow stripes | Marketing artifact | Landing page may use `hero-band` whitespace rhythm, but no rainbow treatment. |
| Pricing sub-system (`Inter Display`, `{rounded.pill}`) | No pricing in product | Do not use `Inter Display` or pill radii anywhere. |

### 6.2 Design tokens that fail accessibility

- `{colors.hairline}` (#dddddd) is **1.36:1** on white — a divider, never an
  input boundary. See §5.1.
- `{colors.border-strong}` (#9297a0) is **2.93:1** — disabled states only.
- `DESIGN.md` has **no error color**; use `{colors.signature-coral}` until a
  decision is recorded (§5.1).

### 6.3 Other traps

| Trap | Detail |
|------|--------|
| Catalog stacks two splits | 93,698 rows = 65,238 unique `nid`; 28,460 `nid` appear twice (one train row + one dev row, identical content). Always dedupe by `nid` when rendering lists. |
| Mounted sub-app does not run its lifespan | `web.mount("/", frozen.app)` does **not** trigger the frozen app's `lifespan`, so `get_rec()` returns 503. The web app must own the lifespan. See `docs/web/ARCHITECTURE.md` §4.2. |
| Scores are not comparable across requests | Hybrid scores are min-max normalized **per request**. Never render them as a match percentage or compare them across sessions. |
| `weighted_hybrid.pkl` (α=0.8) | Historical record. Not read by serving. Do not use. |
| `models/best_alpha.json` | Also historical (α=0.8). Not the source of truth for serving. |
| `configs/preprocessing.yaml` mentions `publish_date` and `alay_dict.csv` | Neither is used or present. `build_locked.py` reads no date column, and `configs/alay_dict.csv` does not exist in the repo. |
| Thin article metadata | `data/processed/news_processed.parquet` has only `nid, title, abstract, processed_text, category, subcategory, split`. No URL, publication date, author, or image. Kebalikannya di korpus aktif: punya `content`, `source`, `published_at`, `url`; tidak punya `abstract`/`subcategory` (lihat §2.3 `DATA_MODEL.md`). |
| `data/web.db` is **not** gitignored | `git check-ignore data/web.db` returns nothing. The app database holds emails and password hashes. Add `data/web.db*` to `.gitignore` **before** the first commit that creates it. |
| `docs/web/PRD.md` is superseded | It still describes a topic-onboarding MVP. `PRD_Web_Rekomendasi_Berita.md` §5.2 removes topics. Do not implement from the old file. |
| Two documents use `AC-xx` IDs | `PRD_Web_Rekomendasi_Berita.md` §14 uses AC-01…AC-54; `ACCEPTANCE_CRITERIA.md` uses AC-01…AC-122. 17 IDs collide with **different meanings**. Always name the file when citing an AC until they are renumbered. |

## 6.4 Git hygiene and branch policy

### Never commit these

| Path | Why |
|------|-----|
| `data/web.db`, `data/web.db-shm`, `data/web.db-wal` | Holds user emails and password hashes |
| `.env` | Local credentials (demo persona password) |
| `data/processed/*.parquet`, `data/raw/*` | Research data, regenerated out of band |
| `models/*.pkl`, `*.npy`, `*.npz` | Frozen artifacts, not distributable via git |

`.gitignore` already covers all of the above. Before the first commit that
creates the database, verify:

```bash
git check-ignore -v data/web.db .env    # must print a matching rule for both
git status --short                      # must not list data/web.db or .env
```

If either file is ever tracked, remove it from the index **without deleting the
working copy**:

```bash
git rm --cached data/web.db
```

### Branch policy

| Branch | Purpose |
|--------|---------|
| `develop` | Pre-web-MVP state. **Must not** receive the `docs/web/` work or the web implementation. |
| `feat/web-mvp-docs` | Documentation set for the web MVP (`AGENTS.md`, `.env.example`, `.gitignore`, `docs/web/**`) |
| `feat/web-mvp` (next) | Implementation; branch from `feat/web-mvp-docs` after review |

**Rules (koreksi status 2026-10-27): pekerjaan web MVP sudah melebur ke
`develop`; korpus fase-2 dieksekusi di `feat/dataset-indo-news` dari `develop`.**
- Do not merge the docs branch into `develop` until the documents are approved.
- Implementation work starts from the docs branch, not from `develop`.
- Never force-push or rewrite `develop`.

## 6.5 Settled decisions (2026-10-20)

Do not reopen these without explicit approval. Implementation must follow them.

| Area | Decision |
|------|----------|
| PRD | `PRD_Web_Rekomendasi_Berita.md` is the only active PRD. `PRD.md` is SUPERSEDED (archive only). |
| AC namespaces | `PRD-AC-01…54` (PRD §14) and `TEST-AC-001…999` (`ACCEPTANCE_CRITERIA.md`). The old bare `AC-xx` namespace is retired; never cite it. |
| Scope | No topic selection, no ratings/likes, no search, no reading duration, no retraining, `view` events only. |
| Process model | One process: web app mounts the frozen API at `/` (mounted last). |
| D13 seam | Additive `load_recommender()` in `src/api/main.py` only. No route/schema/algorithm/α changes; additions-only diff; four proofs required (`ARCHITECTURE.md` §4.2.1). |
| Storage | SQLite at `data/web.db`; gitignored. |
| Session TTL | 7 days. |
| History | Last 50 unique `nid`, then filter results against the **full** history. |
| Feed size | Request `top_k=30`, filter, dedupe, keep API order, render ≤ 10. |
| No-history feed | Popularity computed **once at startup** from `interactions_train.parquet` (sum of `weight` desc, `nid` asc tie-break, catalog-only), cached in memory; no `popular.json`; fail loudly if the parquet is missing; never at import time. Labeled "Berita populer". |
| View events | One `view` per **successfully displayed** detail page. Refresh/re-navigation = new view. Prefetch/background fetch = no view. **No time-window dedupe.** Retries, if added, require a unique `event_id` with an idempotency constraint. |
| Persona | `WEB_DEMO_PERSONA_USER_ID` from env; created only by `python -m src.web.seed_persona` (idempotent); never at startup. |
| Scores | Never rendered anywhere. No debug page in MVP. |
| `/similar` | Detail page only. |
| Error color | `--color-error` = `signature-coral` #aa2d00 (D25). |
| Article body | 16px/1.6 via `.article-body`; all else keeps tokens (D26). |
| Hover | Five token-only changes, ≤ 120 ms; focus always visible (D27). |
| Korpus fase 2 | PRD v1.1 (2026-10-27): korpus portal Indonesia + interaksi simulasi dummy (`view` saja, tanpa like/durasi/rating); kontrak API dan field `nid` dipertahankan. PRD v1.0 tetap mengikat untuk korpus MIND yang beku. Status: **disetujui 2026-10-27**; implementasi fase-2 selesai (Task 0–14 plan fase-2). |

## 7. Definition of Done for Web-Layer Work

- Every approved acceptance criterion in `docs/web/ACCEPTANCE_CRITERIA.md` passes.
- API contract v1.0.0 is unchanged (proven by `test_openapi_contract_surface`
  plus the `docs/openapi.json` snapshot).
- No changes to model artifacts, configuration, or evaluation numbers.
- Documents in `docs/web/` are updated when decisions change.
- **Design compliance:** every rendered screen uses only tokens from
  `docs/web/DESIGN.md`; no CDN fonts; no images or authors — sumber/tanggal
  hanya sejauh katalog aktif menyerakannya secara nyata (PRD v1.1);
  no pricing components; no topic rail; focus states present on all interactive
  elements.

