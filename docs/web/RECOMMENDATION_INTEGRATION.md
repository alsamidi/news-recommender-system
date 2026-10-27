# Recommendation Integration — Web Layer ↔ Frozen Model

Status: **DRAFT — not approved.**
Date: 2026-10-20.
Revised: **2026-10-27 — peralihan korpus (PRD v1.1).** Referensi `U10022`,
`interactions_train.parquet`, dan angka 93,698 adalah **pengukuran era MIND** yang
tetap sah untuk riset v1 yang beku; korpus aktif (Detik/Tempo/Kompas + interaksi
simulasi dummy) adalah korpus baru — lihat PRD v1.1 §0 dan
`data/DATASET_LOCK_INDO.md`. Aturan integrasi (golden rules, routing, filter
histori) TIDAK berubah bentuk.

This document is the **only** place describing how the web layer uses the
model. The API contract, dataset, hybrid configuration, artifacts, and
evaluation numbers are **not duplicated** here — their references are:

| Topic | Authoritative source (do not copy) |
|-------|-----------------------------------|
| API contract v1.0.0 | `docs/API_CONTRACT.md`, `docs/openapi.json` |
| Dataset & sha256 | `data/DATASET_LOCK.md` |
| Hybrid configuration (α) | `configs/hybrid.yaml` |
| Model artifacts | `README.md` §Models, `models/*` |
| Evaluation numbers | `models/full_catalog_eval.json`, `models/stratified_eval.json`, `docs/metrics_source_of_truth.md` |
| Freeze | `docs/RESEARCH_FREEZE.md` |
| Scoring implementation | `src/models/hybrid/infer.py` |

---

## 1. Golden Rules

1. **The web layer does not compute scores.** No TF-IDF, no dot product, no
   normalization inside `src/web/`.
2. **The web layer does not load model artifacts.** Only the frozen API does.
3. **The web layer does not reorder or alter** `recommendations`.
4. **The web layer never sends `alpha`.** That field does not exist in
   `RecommendRequest` and is guarded by `test_openapi_contract_surface`.
5. **The web layer never sends `model`** other than the default `"hybrid"`.

## 2. Two Modes, One Endpoint

`POST /recommend` accepts **exactly one** of `user_id` or `history`.

| Mode | Payload | Requirement | Response mode |
|------|---------|-------------|---------------|
| **Warm** | `{"user_id": "U10022"}` | `user_id` exists in the ALS `user_map` (15,608 users) | `"warm"` |
| **Cold / session** | `{"history": ["N52622", "N40839"]}` | ≥1 `nid` exists in the catalog | `"cold-session"` |

Consequences the web layer must understand:

- `user_id` is **not** a web account. It is a research-dataset user ID (MIND
  era: `U10022`; korpus aktif: ID akun dummy korpus Indo — lihat PRD v1.1 §18).
- Sending a `user_id` without ALS factors → **404**, not a fallback. (F-06)
- Empty `history` → **400**. All-unknown `nid` → **400**.
- Sending both → **400**.

## 3. Routing Decision (to be implemented by the web layer)

```python
def build_request(user, history_nids):
    if history_nids:
        return {"history": history_nids[:50], "top_k": 30}      # cold, history
    return None                          # -> topic slice or popular feed (D8)
```

The web layer then filters results against the user's **full** history (§5.4)
and takes the top 12. `top_k=30` leaves room so that 12 cards remain after
filtering.

Priority: **history → topic slice → popular**.

Two changes from the original design:

1. **No warm path from the web layer** (v1.3): the dataset-persona feature was
   removed, so the app never sends `user_id`. `POST /recommend` still accepts it
   per contract v1.0.0 — only this client stopped using it.
2. **Topic selection exists, but never reaches the API** (v1.2): a 0-view user
   who chose topics gets a category slice of the *frozen popularity list*, with
   no `/recommend` call, no score and no re-ranking. An earlier draft routed
   topic chips into `history`; that remains withdrawn.

### 3.1 Why history wins over the topic slice

A user with history has demonstrated a real signal; the topic preference is a
one-time statement made before reading anything. Sending both would also be
impossible: the API rejects a payload with both `user_id` and `history`, and the
topic slice is a web-side filter rather than a request field. Once one article
is opened, the preference becomes inert (C6).

### 3.2 Why history is capped at 50

Latency is flat up to 400 `nid` (F-23), but a large `history` inflates the
payload without adding signal (the profile is a mean vector; the pseudo-CF is a
mean of factors). The last 50 items are enough and keep the request small.
**D9** sets the final number.

**The cost of this cap:** items outside the 50-item window are not masked by the
API, so the web layer must filter them again (§5.4). The alternative — sending
the entire history — removes the need for filtering but grows the payload. For
demo users (< 100 reads) both are cheap; **D9** may choose "send everything".

## 4. Popularity Path (no-history feed)

When a user has no history, the feed does **not** call
`/recommend`. It renders a popularity list computed from the research data.

### 4.1 Source and definition — APPROVED 2026-10-20

| Item | Value |
|------|-------|
| Source | `data/processed/interactions_train.parquet` (read-only; era MIND. **Korpus aktif:** parquet interaksi simulasi korpus Indo — path final dicatat di `data/DATASET_LOCK_INDO.md` pada tahap generator) |
| When computed | **Once at application startup**, then cached in memory |
| Definition | `nid` sorted by **descending summed `weight`** (korpus aktif: `view` simulasi, weight=1/event) |
| Tie-break | `nid` ascending (deterministic) |
| Catalog filter | Only `nid` present in the catalog are kept |
| Catalog | Era MIND: `news_processed.parquet`. Korpus aktif: katalog korpus Indo, path final per lock |
| Artifact | **None.** No `popular.json`, no new file under `models/` |
| Failure mode | Missing/unreadable parquet → startup fails with a clear message |

Rules fixed by this decision:

- **Not** at module-import time. Importing `src.web.*` must have no I/O side
  effects; the computation belongs in the app lifespan.
- The ranking is computed from the parquet already in memory; no per-request
  re-read and no per-request re-sort.
- Frozen recommender artifacts and the API contract are untouched.
- `weight` (not row count) is the definition. Both produce the same top-10
  (verified 2026-10-20), but `weight` matches the model's implicit-strength
  notion and is now the specified one.
- Coverage: 7,713 distinct `nid` have at least one train click, so the popular
  feed has ample depth beyond the 10 shown.

### 4.2 Rules

1. The list is **not model output** and must be labeled "Berita populer"
   (PRD §16).
2. It is still filtered against the user's full history (usually empty on first
   visit) and deduped by `nid`.
3. Load the parquet **once at startup** (0.19 s, 234,468 rows) into an in-memory
   ordered list. Do not re-read per request. Importing the module must not
   trigger this read.
4. Reading the parquet is allowed; **writing** to it is forbidden
   (PRD §8.1).
5. No score is rendered for these cards.
6. If the parquet is unavailable, startup fails loudly rather than silently
   serving an empty feed — a missing popularity source is a deployment error,
   not a user-facing state.

### 4.3 Why not topic seeds

An earlier draft mapped topic chips to `category` values and used the resulting
`nid` set as a `history` seed. That is withdrawn: topic selection is out of MVP
scope (PRD §5.2, §18), and 3 of the 5 Figma topics have no valid `category`
counterpart (`UX_FLOWS.md` §5.3).

## 5. Response Limitations the Web Layer Must Know

### 5.1 Content-only fallback is indistinguishable from a normal response

`RecommendResponse` only carries `recommendations, model_used, alpha, mode`.
When no session item exists in the ALS space, `HybridRecommender.recommend_session`
falls back to content-only, but `mode` stays `"cold-session"`.

**Verified:** both cases produce identically shaped responses.

**Options for the web layer:**

| Option | Approach | Note |
|--------|----------|------|
| a | Accept as-is, add no special label | Most honest, simplest |
| b | Web computes whether any session `nid` is in the ALS space | Requires `item_map` → violates "web does not load artifacts" |
| c | Add a field to the API (e.g. `cf_available`) | **Changes the frozen contract** → requires a version bump |

**MVP recommendation: (a)**, with the documented caveat that quality can drop
invisibly. If a label is required, choose (c) and treat it as a formal contract
change.

### 5.2 Scores are not comparable across requests

`_minmax` normalizes per request. A score of `0.48` in one session does not mean
"better" than `0.52` in another.

**UI rule (D22, approved 2026-10-20): no score is rendered anywhere in the UI —
not as a percentage, star, progress bar, or raw number. There is no debug page
in MVP scope.** Score inspection happens in tests and internal tooling only.

### 5.3 Dedupe

The API already dedupes by `nid` for presentation (`_select`). The web layer
**must still** dedupe because:
- merging results from multiple calls (e.g. feed + similar) can collide;
- the catalog stores 28,460 duplicate `nid` values (F-03).

### 5.4 Truncating `history` breaks the "already read" guarantee

The API masks **only** the `nid` values sent in `history`. If the web layer caps
history at the last 50 items (D9), articles read earlier are **not** masked and
can reappear in the feed.

**Verified empirically** (probe 2026-10-20, synthetic 80-item ALS session):

| History sent | Do the first 30 (older) articles reappear? |
|--------------|--------------------------------------------|
| Last 50 | **Yes** |
| All 80 | No |

**Consequence:** the web layer must apply a second-layer filter — remove from
`recommendations` every `nid` present in the user's **full** history, not just
the 50 that were sent.

**Accepted side effect:** after filtering, the card count may be < 10. The web
layer may request a larger `top_k` (e.g. `top_k=30`) and then take 10 after
filtering, or render whatever remains. **Recommendation:** request `top_k=30`,
filter, take 10. This changes neither scores nor relative order — it only drops
already-read items.

**Never** filter history *before* sending (e.g. dropping non-ALS items): that
alters the model input, so results no longer match the evaluation.

## 6. Using the Other Endpoints

| Endpoint | Web usage | Note |
|----------|-----------|------|
| `GET /article/{nid}` | Article detail page | Single source of `title/category/content/source/published_at` (korpus aktif; tidak ada `abstract`/`subcategory` — PRD v1.1 §10.2). 404 → "not found" page |
| `GET /similar/{nid}?top_k=5` | "Berita serupa" block | TF-IDF neighbours; the query article never appears (F-08). ~70 ms |
| `GET /health` | Health check / badge | `alpha`, `catalog_size`, `als_items` |

The API's `GET /` is the P3.2 demo viewer and is **outside the contract**. The
web layer registers its own `/` route first, so it wins (verified in
`ARCHITECTURE.md` §4.1).

## 7. Error Handling

| API status | Cause | Web behavior |
|------------|-------|--------------|
| 400 | Empty `history` / all `nid` unknown / both fields set / wrong `model` | Do not surface the raw error. Feed → fall back to the popular list. Log as an internal bug if unexpected |
| 404 | `user_id` without ALS factors; unknown `nid` | For `user_id`: routing bug → fall back to `history`. For articles: 404 page |
| 422 | Invalid schema (`top_k` outside 1–100, wrong types) | Internal bug; should never happen |
| 503 | Model not loaded | "System is starting" page + retry; **never** show a stack trace |

## 8. Invariants to Test on the Web Side

| # | Invariant | How to test |
|---|-----------|-------------|
| I1 | Web payload passes the `RecommendRequest` schema | Validate with Pydantic against the API model |
| I2 | Web never sends `alpha` | Assert on the built payload |
| I3 | Web never sends `user_id` and `history` together | Router unit test |
| I4 | `recommendations` order is unchanged | Compare input vs output `nid` lists |
| I5 | `nid` in the **full** history never reappears in the feed | Assert empty intersection against the whole DB history, not just the 50 sent (§5.4) |
| I6 | `top_k` is always within 1–100 | Assert the constant (30) |
| I7 | API contract unchanged | `test_openapi_contract_surface` + diff of `docs/openapi.json` |
| I8 | α comes from the active research config, never from the web | `test_serving_alpha_matches_table_b_winner` (era MIND); nilai korpus baru mengikuti konfigurasi korpus |

## 9. Prohibited Actions

| Prohibition | Reason |
|-------------|--------|
| Retraining the model on web interactions | Artifacts and report numbers would no longer be valid |
| Adding a new vector table for "personalization" | Duplicates and diverges from frozen artifacts |
| Persisting `score` to the DB and re-ranking with it | Scores are unstable across requests |
| Claiming star ratings "improve recommendations" | The frozen model does not use them |
| Altering `history` before sending (e.g. dropping non-ALS items) | Changes model input → results no longer match the evaluation |
| Calling `HybridRecommender` directly from `src/web/` | Bypasses the contract and validation |

## 10. Reading the Evaluation Numbers Correctly (for UI/docs copy)

Summary, without replacing the numbers (source:
`docs/metrics_source_of_truth.md`):

- The task is hard: 93,698 catalog rows, median 1 relevant item per user.
- Hybrid α=0.4 wins on the full catalog, but **the margin is small** for warm users.
- For cold users the advantage is larger, **but** it holds only on the subset
  that has ALS items.
- **Never** claim "high accuracy". The valid claim is: "α=0.4 is the winner of
  the tested full-catalog protocol".

**Corpus note (2026-10-27):** all numbers above are MIND-era and stay frozen for
research v1. Angka korpus aktif baru dinyatakan setelah evaluasi korpus Indo
selesai; jangan mencampur atau membandingkan dua protokol tanpa mencantumkan
ketergantungan pada interaksi simulasi.

## 11. Integration Validation Plan

1. `pytest` still shows ≥ 26 passing (research regression).
2. `bash scripts/audit_freeze.sh` → `RESEARCH FREEZE AUDIT PASSED`.
3. New web smoke test: register → login → feed → detail → history,
   using `TestClient` with the model loaded once.
4. Parity test: for one demo user, the web feed must yield `nid` values
   identical to `HybridRecommender.recommend_*` for the same payload.
5. Test 404/400/503 per the table in §7.

## 12. Open Integration Decisions

All integration decisions are **settled** (2026-10-20).

| ID | Decision | Status |
|----|----------|--------|
| D21 | Do **not** add a response field for the content-only fallback (option a) — the contract stays unchanged, the UI simply makes no ALS claim | ✅ Approved |
| D22 | No score rendered anywhere; no debug page in MVP | ✅ Approved |
| D23 | History cap: 50 unique `nid`, then filter against the full history | ✅ Approved |
| D24 | `/similar` only on the detail page, never in the feed | ✅ Approved |

## 12b. Topic slot in the routing order (PRD v1.2)

Routing priority, with the exact conditions (not just a position in a list):

1. history non-empty -> cold `/recommend` with `history`;
2. otherwise, 0 views **and** stored topics -> topic feed:
   `slice_by_topic(frozen_popularity)`, label "Populer di topik pilihanmu";
3. otherwise -> "Berita populer" from the same frozen list.

(The persona/warm branch is gone in v1.3, so this is the complete order.)

Step 3 is the only branch that can be confused with "personalisation", so the
constraints are explicit: **no** `POST /recommend`, **no** α, **no** score, no
re-ranking. The only operations added are a category filter over the frozen
ranking, a round-robin interleave (`q = ceil(12/m)`), and a global top-up when
a topic pool is exhausted. Two users with the same topic set receive the same
order, because `user_topics.position` is the canonical chip order rather than
the order the browser happened to submit.

## 13. Corpus Transition (2026-10-27, per PRD v1.1)

- Katalog aktif berganti ke korpus Indo; field UI kini `title, category,
  content, source, published_at` (tanpa abstract/subkategori).
- Interaksi CF berasal dari simulasi akun dummy (`view` saja). Reader-count
  era MIND (`× via MIND`) diganti sumbernya ke unik-pembaca simulasi; label
  produk menyesuaikan (PRD v1.1 §18; TEST-AC-255/256).
  **Label yang dipakai (diputuskan saat implementasi, 2026-10-27):**
  korpus indo merender `× via simulasi` dengan tooltip
  "Akun simulasi unik yang membaca berita ini di dataset (train+dev); bukan
  pembaca nyata"; era MIND (`SERVING_ERA=mind`) tetap `× via MIND`.
  Keduanya dipilih dari `recommender_data["era"]`, bukan dari cabang di
  template per halaman.
- **Sumber & tanggal terbit (PRD v1.1 §10.2).** Kontrak API v1.0.0 tidak
  punya field untuk keduanya (`ArticleDetailResponse` hanya
  title/abstract/category/subcategory), dan menambahnya butuh bump versi.
  Karena itu web membaca katalog aktif langsung (`src/web/services/
  catalog_meta.py`, pola yang sama dengan `popular.py`/`stats.py`), sekali
  saat startup: `nid → source, published_text`. Tidak ada skor, tidak ada
  penulis, tidak ada tautan portal, dan tidak ada angka jumlah artikel yang
  ditulis di kode.
- **Kartu = judul + meta (kategori/sumber/tanggal).** PRD §10.2 melarang
  cuplikan isi di kartu, karena korpus tidak punya abstrak. Kartu feed,
  blok "Berita serupa", dan baris histori memakai satu partial
  (`templates/_card.html`) agar tidak ada varian kartu ketiga.
- Semua aturan web-side seperti routing, top_k=30, filter histori penuh,
  dedupe, tanpa skor — **tidak diubah** oleh migrasi ini.
