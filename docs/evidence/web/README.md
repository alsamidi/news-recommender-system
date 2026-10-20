# Web MVP — Demo Evidence

Captured 2026-10-20 against a live `uvicorn web.app:app` instance on port 8101
with a throwaway database. Screenshots are 1800×1250 (1440×1000 viewport at
1.25 DPR).

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
