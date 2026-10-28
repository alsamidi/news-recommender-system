# Web MVP — Demo Evidence

Captured 2026-10-20 against a live `uvicorn web.app:app` instance on port 8101
with a throwaway database. Screenshots are 1800×1250 (1440×1000 viewport at
1.25 DPR).

## Indo-era evidence (2026-10-27)

Captured against a live `uvicorn web.app:app --app-dir src` instance with a
throwaway database, after the phase-2 corpus swap and the PRD v1.2 topic
feature. Same 1800×1250 / 1440×1000 at 1.25 DPR.

| File | State | What it proves |
|------|-------|----------------|
| `11_feed_popular_indo.png` | Feed, no history, indo corpus | Label **"BERITA POPULER"**, 10 cards, card meta = category + `Sumber:` + date, no excerpt, counts labelled `× via simulasi`. |
| `12_article_detail_indo.png` | Article detail | Title, category, `Sumber:`, `Tanggal:`, full `content`, "Berita serupa" block. No author, no portal link, no image. |
| `13_history_indo.png` | History | Three rows, each exactly four grid cells (title / category+source+date / Dibaca / counts); column left edges identical across rows (TEST-AC-257). |
| `14_feed_after_history_indo.png` | Feed after reading | Label **"REKOMENDASI DARI RIWAYAT BACAANMU"**, already-read nids excluded. |
| `15_onboarding_topik.png` | Topic onboarding | 12 measured chips, max 3, "Lewati" present, optional screen. |
| `16_feed_topik.png` | Topic feed (0-view user) | Label **"POPULER DI TOPIK PILIHANMU"**, cards alternating Politik/Hukum (round-robin), no `/recommend` call. |

Measured in-browser, not estimated: topic chip radius 6px
(`--radius-sm`), border `rgb(65,69,77)` = `--color-muted` (14.6:1), height
45px, focus ring 2px `#458fff`; history row column left edges 610 / 866 /
1092 identical on every row.

## Reading-column evidence (2026-10-29, D31)

| File | State | What it proves |
|------|-------|----------------|
| `21_detail_kolom_tengah.png` | Article detail, desktop 1440px | Breadcrumb, 36px headline, meta line, body and portal link all share one centred column |

Measured in-browser at 1440×1000 (1.25 DPR), not estimated: the
`.article-column` box is x 432→1008 (576px wide), and the breadcrumb,
`.article-headline`, `.meta-row`, `.article-body` and `.article-source` boxes
all report the same left edge 432 and width 576. Headline computed font-size
36px; body 16px with `chars_per_line = 73` measured through a range over the
rendered text (was 78 at the previous 1184px block). The related
`.card-grid` stays at x 128→1312 (1184px), i.e. outside the column. At 390px
viewport the column collapses to 358px starting at x 16 with the headline back
at its 32px mobile size, so nothing changed there.

## Screenshots

| File | State | What it proves |
|------|-------|----------------|
| `01_register.png` | Register form | Fields: Nama, Email, Password, Ulangi Password. No topic step. |
| `02_feed_popular.png` | Feed, no history | Label **"BERITA POPULER"**, 10 cards, category + title only, no thumbnails. |
| `03_article_detail.png` | Article detail | Title, category, abstract. No author, no date, no publisher, no image. |
| `03b_article_related.png` | Detail, related block | "Berita serupa" from `/similar`; the opened article is absent from it. |
| `04_history.png` | History | Two viewed articles, newest first, with view timestamps. |
| `05_feed_cold.png` | Feed after reading | Label **"REKOMENDASI DARI RIWAYAT BACAANMU"**, previously read nids excluded. |
| `06_404.png` | Unknown nid | Friendly 404 with a link back; no traceback. |
| `07_mobile_menu.png` | 375px, menu open | Nav collapses to a burger below 768px; the panel stays inside the viewport. |
| `08_breakpoint_desktop.png` | 1440px | 3-column grid. |
| `09_breakpoint_tablet.png` | 900px | 2-column grid. |
| `10_breakpoint_mobile.png` | 375px | 1-column grid, no horizontal overflow. |

Labels render uppercase through CSS (`text-transform`); the underlying copy in
the templates is title case as specified in PRD §16.

## Database state after the walkthrough

```sql
SELECT COUNT(*) FROM interactions;   -- 2
SELECT nid FROM interactions ORDER BY created_at;
-- N55689, N17741
```

Two navigations → two `view` rows, matching the approved semantics
(no time-window dedupe). Opening `N000_nope` added nothing, confirming that a
404 does not record a view.

## Reproduce

```bash
bash scripts/smoke_web.sh          # automated equivalent of the above
# or manually:
WEB_DB_PATH=/tmp/demo.db uvicorn web.app:app --app-dir src --port 8101
```

## Not captured here

- Warm persona feed screenshot: covered by `smoke_web.sh` scenario B, which
  asserts the "Rekomendasi berdasarkan profil dataset demo" label and 10 cards.
- Breakpoint behaviour is now captured (07–10) and measured: 3 columns at
  1440/1100, 2 at 900, 1 at 700/375; `document.scrollWidth == innerWidth` at
  every width, so nothing overflows.
