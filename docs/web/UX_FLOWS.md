# UX Flows — Web Layer for the News Recommender

Status: **DRAFT — not approved.**
Design source: Figma `8vH3wuK6rRMwQASuvSt1uc` (file "Untitled", Page 1).
Figma audit date: 2026-10-20.

---

## 1. How the Figma File Was Audited (and Its Limits)

Figma exposes no public API without a token, and its canvas renders as a
bitmap. Frame contents were extracted through Figma's **layer tree** (viewer
access), which names layers after their text, plus per-frame SVG export.

**Verified:** frame list, layer order, label text, frame dimensions.
**Not verified:** prototype links between frames (the Prototype panel is
unreadable without login) and final color/typography values. Therefore
**every transition in §3 is a proposal**, not a copy from Figma.

## 2. Figma Frame Inventory

All frames are **1440 × 1024** except the two long pages.

| # | Figma layer name | Size | Type | Note |
|---|------------------|------|------|------|
| 1 | `Landing` | 1440×1024 | Page | **Contains only `Rectangle 1`** — effectively empty |
| 2 | `Login (can be adjusted again whether using email or username to login)` | 1440×1024 | Page | Login card |
| 3 | `Register (can be adjusted again the field needed to register)` | 1440×1024 | Page | Register card |
| 4 | `Pilih Topik` | 1440×1024 | Page | Topic onboarding — **not built in MVP** (PRD §5.2); kept here as reference only |
| 5 | `rekomendasi awal (only for references)` | 1440×1369 | Long page | Recommendation feed |
| 6 | `halaman collaborative filtering (only for references)` | 1440×1369 | Long page | Feed variant (CF label) |
| 7 | `(example only! adjust based to available feature on codebase!)isi berita` | 1440×2187 | Long page | Article detail |

The layer names of 5, 6, and 7 carry the designer's own annotations:
**"only for references"** and **"example only! adjust based to available feature
on codebase!"**. The design is therefore explicitly **not a final spec** and was
intended to be adapted to what the code can do.

### 2.1 Per-Frame Layer Structure (extraction result)

**Login** — centered card:
`LOGIN` (heading) · `goodnews` (brand) · `Email` · `Password` · `LOGIN` (button) ·
`Rectangle 2..6` (decoration/card).

**Register** — centered card:
`REGISTER` (heading) · `goodnews` · `Nama` · `Email` · `Password` ·
`Ulangi Password` · `REGISTER` (button) · `Rectangle 2..8`.

**Pilih Topik** — *reference only; not implemented* — header + card:
`Pertama, pilih beberapa topik favorit kamu!` (heading) ·
`Kami menggunakan topik yang kamu pilih untuk memberikan rekomendasi berita yang
sesuai dengan minat kamu!` (description) ·
chips: `Olahraga`, `Teknologi Informasi`, `Kesehatan`, `Pendidikan`, `Politik` ·
`Lanjutkan` (CTA). Bottom nav: `Telusuri`, `Profil`.

**rekomendasi awal** — feed:
`Rekomendasi Berita` (heading) ·
`Berdasarkan topik yang kamu pilih, inilah berita yang kami rekomendasikan untuk kamu!` ·
`List berita:` · `Berikan rating agar kami bisa memberikan rekomendasi yang lebih menarik` ·
3 identical article cards containing: title `Irak Vs Yordania: Selebrasi Makan
Aymen Hussein Berujung Petaka`, `Kategori: Olahraga`, `Sumber: detik.com`,
`Beri Rating:` + `stars`, `Baca Selengkapnya...`, image `ayman-hussein_169 1..3`.

**halaman collaborative filtering** — feed variant:
`Berita yang disukai oleh pengguna yang mirip denganmu` (heading) ·
`Berita yang dibaca oleh pengguna lain juga dan mungkin kamu tertarik membacanya!` ·
3 identical article cards (same as above).

**isi berita** — detail:
`Irak Vs Yordania: Selebrasi Makan Aymen Hussein Berujung Petaka` (title) ·
long abstract paragraph · `Penulis: Bayu Baskoro` · `Tanggal: 29-01-2024` ·
`Kategori: Olahraga` · `Beri Rating:` + `stars` ·
`Orang lain juga membaca:` + 2 related cards · breadcrumb `Beranda`.

### 2.2 Visible Global Navigation

The header carries the `goodnews` brand and, on `Pilih Topik`, the items
`Telusuri` and `Profil`. There are no dedicated frames for `Telusuri` or `Profil`.

## 3. Proposed Flows (PROPOSAL — not from Figma)

Notation: `[F-n]` refers to features in `PRD.md` §6.

### 3.1 Primary MVP Flow (Happy Path)

Aligned with `PRD_Web_Rekomendasi_Berita.md` §6 and §18: **there is no topic
selection step.** Personalization begins from reading behavior.

```
Landing
  ├─ (no account yet) ──► Register ──► Feed (popular) ──► Detail ──► History
  └─ (has account)    ──► Login    ──► Feed (popular or from history)
                                          ▲                        │
                                          └── next recommendations ┘

Persona account ──► Login ──► Feed (warm, from dataset profile)
```

### 3.2 Step Detail

| # | Screen | User action | System | Data written |
|---|--------|-------------|--------|--------------|
| 1 | Landing | Click "Daftar" / "Masuk" | Route to Register/Login | — |
| 2 | Register | Fill name, email, password, repeat password | Validate, create account, start session | `users` |
| 3 | Feed | View up to 10 cards | No history → popular list. History → `POST /recommend` (§4) | — |
| 4 | Detail | Click "Baca Selengkapnya" | `GET /article/{nid}`; record the read | `interactions` |
| 5 | Detail | View "Berita serupa" | `GET /similar/{nid}` | — |
| 6 | History | Open the History menu | Read the user's `interactions` | — |
| 7 | Feed | Return to the feed | Recommendations recomputed from history | — |
| 8 | — | Log out | Destroy the session | — |

### 3.3 Alternative and Edge Flows

| Condition | Behavior |
|-----------|----------|
| User has no history | Feed shows 10 popular train articles labeled "Berita populer" (not model output) |
| Empty history | Popular feed, never an error; history page shows a dedicated empty state |
| History contains only non-ALS articles | `recommend` returns content-only while `mode` stays `cold-session`; the UI must not claim ALS was used |
| Very long history | Send the last 50 unique `nid`, then filter against the **full** history (§`RECOMMENDATION_INTEGRATION.md` §5.4) |
| Dataset persona account | Warm feed via `user_id`; app history still recorded but never mixed into the warm payload |
| Persona invalid (404) | Fall back to history if present; otherwise a controlled error page |
| Article with no `abstract` (5.0%) | Detail renders `title` + category with "Ringkasan tidak tersedia untuk berita ini." |
| Unknown `nid` | 404 from the API → friendly "article not found" page; **no** interaction row written |
| Expired login session | Redirect to Login, preserving the target URL |

## 4. UI → API Integration Points

| Screen | Endpoint | Payload | Mode |
|--------|----------|---------|------|
| Feed (user with history) | `POST /recommend` | `{"history": [nid,...], "top_k": 30}` | `cold-session` |
| Feed (dataset persona) | `POST /recommend` | `{"user_id": "...", "top_k": 30}` | `warm` |
| Feed (no history) | — (no API call) | popular list from train click counts | — |
| Detail | `GET /article/{nid}` | — | — |
| "Berita serupa" | `GET /similar/{nid}?top_k=5` | — | — |
| Health/badge | `GET /health` | — | — |

`top_k=30` (not 10) is required so that ~10 cards remain after filtering out
already-read articles. The web layer then renders at most 10, preserving API
order.

**Hard rule:** the UI must not compute scores, must not reorder results, and
must not render `score` in any form (D22). See `RECOMMENDATION_INTEGRATION.md`.

## 5. Figma ↔ Data Fit (Detail)

This section answers the request to "check whether the Figma features match the
news data that is actually available".

### 5.1 Available and Directly Usable

| Figma element | Source column | Coverage |
|---------------|---------------|----------|
| Article title | `title` | 100% (65,238 unique `nid`) |
| Article body | `abstract` | 95.0% populated; mean 218 characters |
| `Kategori:` | `category` | 100%, 18 values |
| Subcategory (not shown in Figma, but available) | `subcategory` | 100%, 270 values |

### 5.2 Not Available

| Figma element | Status | Evidence |
|---------------|--------|----------|
| `Sumber: detik.com` | **Absent.** No publisher/source column exists. Raw MIND URLs exist in `news.tsv` but their domain is `assets.msn.com` and they never reach the parquet | F-16 |
| Article images (`ayman-hussein_169 1..3`) | **Absent.** No image/thumbnail column | F-16 |
| `Penulis: Bayu Baskoro` | **Absent.** No author column | F-16 |
| `Tanggal: 29-01-2024` | **Absent.** No per-article publication date; only interaction timestamps exist | F-16 |
| Star ratings | **Absent** from the dataset (implicit clicks only), and **out of MVP scope** (PRD §5.2) | F-17 |

### 5.3 Topic Onboarding Mismatch

Figma offers 5 topic chips. The dataset's real categories are the 18 MIND values.

| Figma chip | Dataset counterpart | Feasibility |
|------------|---------------------|-------------|
| `Olahraga` | `sports` (26,270 rows) | ✅ direct |
| `Kesehatan` | `health` (3,600 rows) | ✅ direct |
| `Politik` | None. Candidate: `news` subset matching political keywords (≈2,277 rows) | ⚠️ needs mapping rule (D1) |
| `Teknologi Informasi` | None. Scattered across `news`, `finance`, `autos`, etc. (≈320 keyword matches) | ⚠️ needs mapping rule |
| `Pendidikan` | None. Scattered (≈2,187 keyword matches) | ⚠️ needs mapping rule |

**Important for CF coverage:** only a small share of items per topic live in the
ALS space (3,394 items, 5.2% of the catalog):

| Topic | Rows | In ALS space |
|-------|------|--------------|
| `sports` | 19,368 | 586 (3.0%) |
| `health` | 2,207 | 215 (9.7%) |
| Politik (keywords) | 2,277 | 206 (9.0%) |
| Teknologi (keywords) | 320 | 15 (4.7%) |
| Pendidikan (keywords) | 2,187 | 100 (4.6%) |

Consequence (and the reason topics were dropped from the MVP): 3 of the 5 Figma
chips have no valid `category` counterpart, and even the two that do map mostly
to non-ALS items — so a topic-seeded feed would frequently fall back to
content-only. **Decision: topic onboarding is out of MVP scope** (PRD §5.2, §18).

### 5.4 Figma Elements That Need New Meaning

| Figma | Problem | Proposed MVP |
|-------|---------|--------------|
| `Orang lain juga membaca:` | The model has no "other users read this" path. What exists is TF-IDF similarity (`/similar`) | Rename to **"Berita serupa"**, sourced from `/similar/{nid}` |
| `Berita yang disukai oleh pengguna yang mirip denganmu` | ALS does capture implicit similarity, but it is not exposed as a "similar users" list | Make it the main feed rather than an explicit claim about "similar users" |
| `Berikan rating agar kami bisa memberikan rekomendasi yang lebih menarik` | The frozen model does not use ratings, and ratings are out of MVP scope | **Do not use this string.** Remove the rating control entirely |
| `Berdasarkan topik yang kamu pilih...` | There is no topic selection in the MVP, so this copy is false | **Do not use this string.** Replace with PRD §16 copy: "Berita populer" or "Rekomendasi dari riwayat bacaanmu" |

### 5.5 Other Mismatches

- **`Landing` is empty.** Only `Rectangle 1`. Needs design from scratch — or
  route straight to Login/Register.
- **Figma's article cards are identical 3×.** No variation, and no empty,
  loading, or error states. The MVP needs those states.
- **No History, Profile, or Search frames.** History is an MVP feature (F8) but
  has no design reference.
- **No responsive indication.** All frames are 1440 px. MVP: desktop-first, with
  one tablet breakpoint.

## 6. Design System Application

Visual authority: `docs/web/DESIGN.md` (tokens). Scope authority:
`PRD_Web_Rekomendasi_Berita.md`. When they disagree, the PRD and data
availability win (see `AGENTS.md` §5.1).

### 6.1 Screen → component mapping

| Screen | DESIGN.md components | Adaptation required |
|--------|---------------------|---------------------|
| Landing | `hero-band`, `button-primary`, `button-secondary` | No rainbow stripes, no demo grids. One primary CTA ("Daftar"), one secondary ("Masuk"). |
| Register / Login | `text-input`, `text-input-focus`, `button-primary`, `label-md` | Add error state (no token exists — use `{colors.signature-coral}`). Card container uses `{rounded.lg}` on `{colors.canvas}`. |
| Feed | `article-card`, `top-nav`, `label-md` | **No thumbnail.** Category tag only. 3-up desktop, 2-up tablet, 1-up mobile. |
| Article detail | `article-card` (for related), `top-nav` | Body text uses `{typography.body-md}` at a comfortable measure (~65–75ch). Related block uses `article-card` without thumbnails. |
| History | `article-card` (compact), `top-nav` | Same card without thumbnail; show `created_at` grouped by day. |
| Error / 404 / 503 | `cream-callout-card` or `signature-coral-card` | Coral for hard errors (503/404), cream for soft empty states. |
| Empty history | `cream-callout-card` | Uses PRD §16 copy: "Kamu belum membuka berita…". |

### 6.2 Article card without a thumbnail

`DESIGN.md`'s `article-card` assumes a 16:9 image. The catalog has none (F-16).
The MVP card is therefore:

```
┌──────────────────────────────────┐
│ OLAHRAGA                          │  ← uppercase category, {typography.caption}
│ Irak Vs Yordania: Selebrasi …     │  ← {typography.title-sm} (18/500)
│                                   │
│ [Baca]                            │  ← optional text link
└──────────────────────────────────┘
```

Rules:
- No `<img>`, no CSS background image, no generated placeholder graphic.
- If a visual anchor is wanted, use a 4px top border in a token color, not a
  fake image area.
- Card background `{colors.canvas}`, `1px` border `{colors.muted}` (not
  `hairline` — 1.36:1 fails non-text contrast), `{rounded.md}`, padding
  `{spacing.md}` (16px).

### 6.3 States the design system does not cover

`DESIGN.md` documents no loading, empty, error, or disabled-card states. These
must be built from existing tokens:

| State | Treatment |
|-------|-----------|
| Loading | Skeleton blocks using `{colors.surface-soft}`, `{rounded.md}`, no animation beyond a slow opacity pulse. |
| Empty | `{colors.signature-cream}` callout + `{colors.ink}` text + one `button-primary`. |
| Error (hard) | `{colors.signature-coral}` surface + white text + retry `button-secondary-on-dark` (D25). |
| Error (field) | `{colors.signature-coral}` 1px border + 14px message below the input (D25). |
| Disabled | `{colors.border-strong}` border, `{colors.muted}` text, no hover. |

### 6.4 Typography and readability — D26 approved

`DESIGN.md` sets body copy at **14px / 400 / 1.25**, tuned for marketing copy
rather than sustained reading.

**Decision D26 (APPROVED 2026-10-20):** the article body renders at
**16px / 1.6**; everything else keeps the token value.

| Context | Size / line height |
|---------|--------------------|
| Article body | 16px / 1.6 |
| UI chrome (nav, meta, buttons, forms) | 14px / 1.25 (`{typography.body-md}`) |
| Card titles | 18px / 1.4 (`{typography.title-sm}`) |

Apply via a single `.article-body` class; do **not** modify the type tokens.
Measure article text at 65–75 characters per line.

### 6.5 Interaction states — D27 approved

`DESIGN.md` documents no hover states. **D27 (APPROVED 2026-10-20)** permits
hover for affordance, restricted to token-only changes:

| Element | Allowed hover |
|---------|---------------|
| Article card | background `{colors.canvas}` → `{colors.surface-soft}` |
| Text link | `{colors.link}` → `{colors.link-active}` |
| Primary button | `{colors.primary}` → `{colors.primary-active}` |
| Secondary button | `{colors.canvas}` → `{colors.surface-soft}` |
| Nav item | `{colors.ink}` → `{colors.muted}` |

Not allowed: transform, scale, translate, added shadow, non-token colors, or
transitions longer than 120 ms.

**Keyboard focus is independent of hover and always visible** (TEST-AC-230/231) —
hovering must never be the only way to perceive interactivity.

### 6.6 Navigation

`DESIGN.md`'s `top-nav` is 64px, white, never inverted. Use it as-is:
- Left: product name.
- Right (authenticated): Feed, Histori, Logout.
- Right (anonymous): Masuk, Daftar.
- Collapses to a menu below 768px.

## 7. UX Principles for the MVP

1. **Never fabricate data.** No invented images, dates, authors, or sources.
   Text-first cards (§6.2).
2. **Explain where recommendations come from.** Each feed carries a source
   label: "Berita populer" / "Rekomendasi dari riwayat bacaanmu" /
   "Rekomendasi berdasarkan profil dataset demo" (PRD §16).
3. **Do not present raw scores as quality.** Scores are not rendered at all in
   the MVP (PRD §18).
4. **Always provide a way out.** Empty feed → popular articles; 404 detail → back
   to feed.
5. **Respect the token set.** No new colors, no pill radii, no CDN fonts
   (`AGENTS.md` §5.1).

## 8. UX Decisions

All items below are **settled**. No open UX questions remain.

| ID | Question | Decision | Status |
|----|----------|----------|--------|
| D8 | What shows when a user has no history? | 10 popular train articles, labeled "Berita populer" (not model output) | Locked by PRD §18 |
| D9 | How many history `nid` values are sent to `/recommend`? | Last 50 unique, then filter against the full history (`RECOMMENDATION_INTEGRATION.md` §5.4) | Locked by PRD §18 |
| D10 | Are star ratings shown in the MVP? | No | Locked by PRD §5.2 |
| D11 | Is topic selection part of the MVP? | No — the "Pilih Topik" flow is withdrawn | Locked by PRD §5.2 |
| D12 | UI language | Indonesian | Locked by PRD |
| D25 | Which error color, given `DESIGN.md` has none? | `{colors.signature-coral}` (#aa2d00), exposed as `--color-error` | ✅ Approved 2026-10-20 |
| D26 | Article body size: 14px (token) or 16px (readability)? | 16px/1.6 via `.article-body`; 14px everywhere else (§6.4) | ✅ Approved 2026-10-20 |
| D27 | Is a hover state allowed, given `DESIGN.md` documents none? | Yes, restricted to five token-only changes; no transform/shadow; ≤ 120 ms | ✅ Approved 2026-10-20 |
