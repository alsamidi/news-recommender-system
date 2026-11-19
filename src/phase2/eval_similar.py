"""CLI: quantify the "Berita serupa" block (article detail, related items).

  PYTHONPATH=. python -m src.phase2.eval_similar

The block is served by `IndoHybridRecommender.similar(nid, top_k=5)` — pure
TF-IDF cosine over `catalog.parquet["processed_text"]` (vectoriser fit on
`catalog_train.parquet`, L2-normalised), no ALS / popularity / personalisation.
Until now it had no quantitative evaluation. This script measures three things
on ONE deterministic sample of query articles:

  category_match@5  : mean fraction of the 5 returned items whose `category`
                      equals the query's `category`.
  coview_recall@5   : mean fraction of the 5 returned items that are
                      "co-viewed" with the query, i.e. the pair shares
                      >= 2 TRAIN accounts (>= 1 variant reported too, so the
                      threshold's effect is visible). Co-view is measured on
                      `interactions_train.parquet` only — the same split the
                      TF-IDF matrix was fit on, and the only history the
                      served system ever saw.
  random_baseline_category_match@5
                    : (1) again, but with 5 items drawn uniformly at random
                      from the catalog (same RNG stream). This is the number
                      the TF-IDF result must be compared against.

Sample: `n_queries` nids drawn with `numpy.random.default_rng(seed)` from the
catalog nids that appear in TRAIN interactions (so co-view is measurable),
then sorted — same seed reproduces the same sample.

Writes docs/evidence/phase2/similar_eval.json (protocol + metrics + by-category
breakdown). Read-only over data/ and models/.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

# src/ on sys.path so `models.*` (imported by phase2.serving) resolves, exactly
# like src/web/app.py does. Then `src.phase2.serving` imports cleanly under
# PYTHONPATH=.
REPO = Path(__file__).resolve().parents[2]
_SRC = REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from src.phase2.serving import load_indo_recommender  # noqa: E402

OUT = REPO / "docs/evidence/phase2/similar_eval.json"

K = 5
N_QUERIES = 300
SEED = 42
COVIEW_THRESHOLD = 2          # headline: pair shares >= 2 TRAIN accounts
COVIEW_THRESHOLD_VARIANT = 1  # sensitivity: pair shares >= 1 TRAIN account
TOP_CATEGORIES = 8


def draw_sample(train_nids: list[str], n: int, seed: int) -> list[str]:
    """Deterministic query sample: uniform over TRAIN-viewed catalog nids."""
    rng = np.random.default_rng(seed)
    cand = sorted(train_nids)
    picked = rng.choice(len(cand), size=n, replace=False)
    sample = sorted(cand[i] for i in picked)
    assert len(sample) == n, f"sample size {len(sample)} != {n}"
    assert len(set(sample)) == n, "sample contains duplicate nids"
    return sample


def build_coview_counts(query_nids: list[str], train: pd.DataFrame,
                        all_nids: list[str]) -> np.ndarray:
    """(len(query_nids) x len(all_nids)) common-account counts.

    Binary item x account matrix, then query rows @ B.T. Dense output is
    ~300 x 13,881 ints, cheap; the full 13.9k x 13.9k matrix would not be.
    """
    pos = {n: i for i, n in enumerate(all_nids)}
    users = sorted(train["dummy_user_id"].unique())
    uidx = {u: i for i, u in enumerate(users)}
    rows = train["nid"].map(pos).to_numpy()
    cols = train["dummy_user_id"].map(uidx).to_numpy()
    b = sp.csr_matrix((np.ones(len(train), dtype=np.int32), (rows, cols)),
                      shape=(len(all_nids), len(users)))
    b.data[:] = 1  # duplicate (nid, user) rows collapse to one account
    q_rows = np.array([pos[n] for n in query_nids])
    counts = b[q_rows] @ b.T
    return np.asarray(counts.todense(), dtype=np.int32)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--n-queries", type=int, default=N_QUERIES)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    k, n_q, seed = args.k, args.n_queries, args.seed

    print("[1/4] loading recommender (TF-IDF fit + ALS pickle, ~20s)...")
    rec = load_indo_recommender()
    nid_pos = rec._nid_pos
    cats = rec._categories

    print("[2/4] loading TRAIN interactions...")
    train = pd.read_parquet(
        REPO / "data/processed/indo/interactions_train.parquet",
        columns=["dummy_user_id", "nid"])
    train = train[train["nid"].isin(nid_pos)]
    train_nids = sorted(train["nid"].unique())
    coview_nids = train_nids  # candidate universe for co-view counts

    sample = draw_sample(train_nids, n_q, seed)
    print(f"      sample: {len(sample)} queries (seed={seed}, unique)")

    counts = build_coview_counts(sample, train, coview_nids)
    col_pos = {n: i for i, n in enumerate(coview_nids)}
    # symmetric counts; the diagonal is the query's own account count and is
    # never scored (similar() excludes the query item itself).

    rng = np.random.default_rng(seed)  # same stream, continues after the draw
    all_nids = rec.full_nids
    n_catalog = len(all_nids)

    cat_hits, cov_hits, cov_hits_1 = [], [], []
    rand_cat_hits = []
    per_cat: dict[str, list[float]] = {}
    per_cat_rand: dict[str, list[float]] = {}

    print(f"[3/4] scoring {len(sample)} queries (k={k})...")
    for qi, qnid in enumerate(sample):
        qcat = cats[nid_pos[qnid]]
        row = counts[qi]

        rel = rec.similar(qnid, top_k=k)
        assert len(rel) == k, f"similar() returned {len(rel)} for {qnid}"
        assert all(r["nid"] != qnid for r in rel), "query item leaked into top-k"

        hits = sum(1 for r in rel if r["category"] == qcat)
        cat_hits.append(hits / k)

        c2 = c1 = 0
        for r in rel:
            j = col_pos.get(r["nid"])
            ov = int(row[j]) if j is not None else 0
            if ov >= COVIEW_THRESHOLD:
                c2 += 1
            if ov >= COVIEW_THRESHOLD_VARIANT:
                c1 += 1
        cov_hits.append(c2 / k)
        cov_hits_1.append(c1 / k)

        # random baseline: k distinct items, query itself excluded
        idx = rng.choice(n_catalog, size=k, replace=False)
        rhits = sum(1 for i in idx
                    if i != nid_pos[qnid] and cats[i] == qcat)
        # if the query was drawn, the draw has k-1 effective items; keep the
        # denominator at k for parity with the served block (rare: k/67k).
        rand_cat_hits.append(rhits / k)

        per_cat.setdefault(qcat, []).append(hits / k)
        per_cat_rand.setdefault(qcat, []).append(rhits / k)

        if (qi + 1) % 50 == 0:
            print(f"      {qi + 1}/{len(sample)}")

    print("[4/4] writing evidence JSON...")
    cat_mean = float(np.mean(cat_hits))
    cov_mean = float(np.mean(cov_hits))
    cov_mean_1 = float(np.mean(cov_hits_1))
    rand_mean = float(np.mean(rand_cat_hits))
    # how many queries even HAVE a >= threshold co-view candidate in the
    # catalog (excluding themselves) — tells whether recall is measurable.
    diag = np.arange(len(sample))
    off = counts.copy()
    off[diag, [col_pos[n] for n in sample]] = 0
    cov_coverage = float(np.mean(off.max(axis=1) >= COVIEW_THRESHOLD))

    top_cats = sorted(per_cat.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    by_category = {
        cat: {"n_queries": len(vals),
              "category_match@5": float(np.mean(vals)),
              "random_baseline_category_match@5": float(np.mean(per_cat_rand[cat]))}
        for cat, vals in top_cats[:TOP_CATEGORIES]
    }

    out = {
        "protocol": {
            "block": "Berita serupa (article detail related items)",
            "served_by": "IndoHybridRecommender.similar(nid, top_k)",
            "method": "TF-IDF cosine over catalog.parquet processed_text; "
                      "vectoriser fit on catalog_train.parquet, L2-normalised; "
                      "no ALS, no popularity, no personalisation",
            "k": k,
            "n_queries": len(sample),
            "sample_seed": seed,
            "sample_frame": "numpy.random.default_rng(seed), uniform without "
                            "replacement over catalog nids present in "
                            "data/processed/indo/interactions_train.parquet, "
                            "then sorted (deterministic)",
            "sample_n_candidates": len(train_nids),
            "catalog_source": "data/processed/indo/catalog.parquet",
            "coview_source": "data/processed/indo/interactions_train.parquet",
            "coview_definition": "candidate and query share >= "
                                 f"{COVIEW_THRESHOLD} TRAIN accounts (distinct "
                                 "dummy_user_id); a pair sharing at least one "
                                 "account is necessary but not sufficient",
            "coview_threshold": COVIEW_THRESHOLD,
            "coview_threshold_variant": COVIEW_THRESHOLD_VARIANT,
            "coview_threshold_variant_definition":
                "same but >= 1 shared TRAIN account (sensitivity check on the "
                "threshold; not the headline)",
            "random_baseline": "k items drawn uniformly without replacement "
                               "from the full catalog with the same RNG stream; "
                               "query item excluded",
            "category_match": "fraction of the k returned items whose "
                              "catalog `category` equals the query's category",
            "coview_recall": "fraction of the k returned items that are "
                             "co-viewed with the query",
            "not_measured": ["coview_precision (undefined: no per-query "
                             "relevant pool)", "self-similarity"],
        },
        "metrics": {
            "category_match@5": cat_mean,
            "coview_recall@5": cov_mean,
            "coview_recall@5_threshold_1": cov_mean_1,
            "random_baseline_category_match@5": rand_mean,
            "category_match@5_lift_over_random": cat_mean - rand_mean,
            "coview_coverage_queries_with_any_coview_candidate": cov_coverage,
        },
        "by_category": by_category,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")

    print(f"\ncategory_match@5            = {cat_mean:.4f}")
    print(f"random_baseline_cat_match@5 = {rand_mean:.4f}  "
          f"(gap {cat_mean - rand_mean:+.4f})")
    print(f"coview_recall@5 (>=2 accts) = {cov_mean:.4f}")
    print(f"coview_recall@5 (>=1 acct)  = {cov_mean_1:.4f}")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
