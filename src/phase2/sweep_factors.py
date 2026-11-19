"""Sweep jumlah faktor ALS di seluruh 9 titik sensitivitas.

  python -m src.phase2.sweep_factors [--factors 16,32,64,128]

Kenapa ada: matriks latih 600 x 13.881 hanya terisi 0,688%, sementara model
128 faktor punya 1,85 juta parameter untuk 57 ribu observasi. Sweep ini
mengukur apakah 128 faktor memang berlebih.

Protokol sama dengan `run_eval`: bangkitkan interaksi per titik (seed x s),
split q80, latih ALS dengan regularisasi/iterasi/alpha/seed yang sama, lalu
hitung NDCG@10 pada peringkat penuh katalog per akun. Yang diubah hanya jumlah
faktor.

Luaran: docs/evidence/phase2/factor_sweep.json (mean dan per titik, plus
popularity sebagai pembanding).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.phase2 import config
from src.phase2.evaluate import (als_ranker, evaluate_ranking,
                                 popularity_ranker, rank_topk)
from src.phase2.generator import generate_interactions
from src.phase2.run_eval import (BASE_SHAPE, EFFECTIVE_SINCE, SEEDS, S_GRID,
                                 effective_catalog)
from src.phase2.split import draft_q80, split_catalog, split_interactions
from src.phase2.train_als import build_csr, fit_als

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs/evidence/phase2/factor_sweep.json"
K = 10


def fit_with_factors(mat, factors: int):
    """ALS with the locked params except the factor count.

    The confidence weight ``c = 1 + alpha * views`` is already baked into the
    CSR by ``train_als.build_csr``. ``implicit`` additionally rescales the
    matrix by the constructor's ``alpha`` inside ``fit``
    (``if self.alpha != 1.0: Cui = self.alpha * Cui``), so passing
    ``alpha=40.0`` here applies the weight TWICE and silently changes the
    factorization. Keep the default ``alpha=1.0`` to stay identical to
    ``train_als.fit_als`` — the earlier sweeps got this wrong.
    """
    import implicit

    model = implicit.als.AlternatingLeastSquares(
        factors=factors, regularization=0.01, iterations=20,
        random_state=42, use_gpu=False)
    model.fit(mat)
    return model


def ndcg(rankings, relevant, accounts):
    return float(np.mean([evaluate_ranking(rankings[a], relevant.get(a, set()),
                                            K)["ndcg@10"] for a in accounts]))


def run_point(gen_seed: int, s: float, factors: list[int]) -> dict:
    catalog = pd.read_parquet(REPO / config.CATALOG_OUT)
    eff = effective_catalog(catalog)
    cfg = config.GeneratorConfig(
        n_accounts=BASE_SHAPE["n_accounts"],
        reads_per_account=BASE_SHAPE["reads_per_account"],
        powerlaw_s=s, recency_days=BASE_SHAPE["recency_days"],
        category_drift=BASE_SHAPE["category_drift"], seed=gen_seed)
    inter = generate_interactions(
        eff[["nid", "category", "source", "published_at"]], cfg)
    cutoff = draft_q80(inter)
    train_i, dev_i = split_interactions(inter, cutoff)
    split_catalog(catalog, cutoff)
    mat, uidx, iidx = build_csr(train_i)

    relevant = dev_i.groupby("dummy_user_id")["nid"].apply(set).to_dict()
    items = sorted(catalog["nid"].unique())
    accounts = sorted(set(dev_i["dummy_user_id"]))

    result = {"seed": gen_seed, "s": s, "n_accounts": len(accounts),
              "als_ndcg10": {}, "popularity_ndcg10": None}
    for f in factors:
        model = fit_with_factors(mat, f)
        rankings = rank_topk(als_ranker(model, uidx, iidx, items), items,
                             accounts, K)
        result["als_ndcg10"][str(f)] = ndcg(rankings, relevant, accounts)

    pop = rank_topk(popularity_ranker(train_i, items), items, accounts, K)
    result["popularity_ndcg10"] = ndcg(pop, relevant, accounts)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.phase2.sweep_factors")
    ap.add_argument("--factors", default="16,32,64,128")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    factors = [int(x) for x in args.factors.split(",")]

    points = []
    for gen_seed in SEEDS:
        for s in S_GRID:
            pt = run_point(gen_seed, s, factors)
            points.append(pt)
            row = "  ".join(f"f{f}={pt['als_ndcg10'][str(f)]:.6f}" for f in factors)
            print(f"seed={gen_seed} s={s}: {row}  pop={pt['popularity_ndcg10']:.6f}",
                  flush=True)

    means = {str(f): float(np.mean([p["als_ndcg10"][str(f)] for p in points]))
             for f in factors}
    best = max(means, key=means.get)
    out = {
        "protocol": {
            "point": "9 titik sensitivitas (seed 1-3 x s 0.9/1.1/1.3)",
            "metric": f"NDCG@{K}, peringkat penuh katalog per akun",
            "factors": factors,
            "als_params": {"regularization": 0.01, "iterations": 20,
                           "alpha": 40.0, "random_state": 42},
            "effective_catalog_since": EFFECTIVE_SINCE,
        },
        "means": means,
        "best_factors": int(best),
        "popularity_mean": float(np.mean([p["popularity_ndcg10"] for p in points])),
        "points": points,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print("\nmean:", {k: round(v, 6) for k, v in means.items()})
    print("terbaik:", best, "faktor")
    print(f"popularity mean: {out['popularity_mean']:.6f}")
    print("->", args.out)


if __name__ == "__main__":
    main()
