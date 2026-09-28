# API Contract (frozen — v1.0.0, Day 6 P3.1)

Serving stack: `HybridRecommender` (`src/models/hybrid/infer.py`) over frozen
artifacts. **α = 0.4 for every served request** — no per-request override —
equal to the full-catalog winner (Table B NDCG@10 0.00208,
`models/full_catalog_eval.json`), enforced programmatically by
`test_serving_alpha_matches_table_b_winner`. Machine-readable snapshot:
`docs/openapi.json` (regen: `python -c "import sys; sys.path.insert(0,'src');
from api.main import app; import json;
json.dump(app.openapi(), open('docs/openapi.json','w'), indent=2)"`).

## Endpoints

| Method & path | Input | Output | Mode |
|---------------|-------|--------|------|
| `GET /health` | — | `HealthResponse` | liveness + serving config proof |
| `POST /recommend` | `RecommendRequest` | `RecommendResponse` | warm (`user_id`) / cold (`history`) |
| `GET /similar/{nid}?top_k=` | nid path, `1 ≤ top_k ≤ 100` | `SimilarResponse` | content neighbours, self excluded |
| `GET /article/{nid}` | nid path | `ArticleDetailResponse` | catalog lookup |

## Schemas

`RecommendRequest`: `user_id?: string`, `history?: string[]` (exactly one
required), `top_k = 10 (1–100)`, `model = "hybrid"` (only value served).

`ArticleResponse`: `nid, title?, category?, subcategory?, score`.
`RecommendResponse`: `recommendations: ArticleResponse[]`,
`model_used = "hybrid"`, `alpha = 0.4`, `mode: "warm" | "cold-session"`.
`HealthResponse`: `status, alpha, catalog_size = 93698, als_items = 3394`.
`SimilarResponse`: `nid, similar: ArticleResponse[]`.
`ArticleDetailResponse`: `nid, title?, abstract?, category?, subcategory?`.

## Examples (real responses, truncated)

`GET /health` → `{"status":"ok","alpha":0.4,"catalog_size":93698,"als_items":3394}`

`POST /recommend {"user_id":"U10022","top_k":2}` → mode `warm`:
`N52622 [sports] 0.4834 "The NFL Hot Seat: Sean McVay kehabisan sihir…"`,
`N40839 [sports] 0.4635 "Stephen Curry memanggil Michael Jordan…"`

`POST /recommend {"history":["N52622","N40839"],"top_k":2}` → mode
`cold-session` (TF-IDF + pseudo-CF). Session without any ALS item returns
mode `cold-session` as well, scored content-only (same response contract).

`GET /similar/N52622?top_k=2` → `N56369 (0.3791)`, `N42964 (0.3501)`;
query article itself never appears.

## Errors

| Code | Trigger |
|------|---------|
| 400 | neither / both of `user_id`, `history`; unknown-nid-only session; empty session; `model != "hybrid"` |
| 404 | `user_id` without ALS factor (message points to `history`); unknown `nid` |
| 422 | schema violation (`top_k` out of range, wrong types) — FastAPI default |
| 503 | recommender not loaded (startup failure) |

## Behavior guarantees (and how each is proven)

- Warm/cold/fallback scoring identical to frozen evaluators (same primitives,
  same op order): `tests/test_hybrid_inference.py` parity tests (exact ranking
  + scores vs evaluator-assembled oracle).
- No leakage: served warm recs contain no train nid; cold recs contain no
  session nid (explicit asserts; re-checked live by `scripts/smoke_demo.sh`).
- No duplicate articles: presentation dedupes by nid (catalog stacks
  train+dev rows, 28.460 nids doubled); scores/order follow the evaluator.
- Already-seen filtering is nid-level (stricter than the evaluator's
  position-level mask); scoring untouched. See `infer.py::_mask_seen`.

## Run from clean state / setup

```bash
source venv/bin/activate          # Python 3.12 venv at repo root
pip install -r requirements.txt   # serving needs fastapi, uvicorn, pydantic,
                                  # pyyaml (+ httpx/pytest for tests only)
uvicorn src.api.main:app --port 8000   # from repo root; loads ~7s once
bash scripts/smoke_demo.sh        # full proof: pytest + live warm/cold/
                                  # fallback/similar/article, exit != 0 on failure
```

Data + artifacts required (frozen, never retrained at serve time):
`data/processed/*.parquet`, `models/tfidf_baseline.pkl`,
`models/als_model.pkl`, `models/als_{user,item}_factors.npy`,
`configs/hybrid.yaml`.

## Freeze rule

This contract changes only with a version bump (`1.0.0` → next), a regenerated
`docs/openapi.json`, and an updated parity/smoke proof. New behavior belongs
behind a new route or version, never silent drift.

Out of contract (viewer, not API): `GET /` serves the P3.2 demo page
(`src/api/templates/demo.html`, `include_in_schema=False`) — thin viewer over
`/recommend` with server-injected presets from frozen artifacts. It never
appears in `docs/openapi.json` (asserted by `test_openapi_contract_surface`).
