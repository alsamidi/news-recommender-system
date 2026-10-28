"""Sweep alpha hybrid sampai 1,0 di seluruh 9 titik sensitivitas.

  python -m src.phase2.sweep_alpha [--factors 64,128]

Kenapa ada: grid resmi berhenti di 0,8. Kalau kurva masih naik di 0,8, nilai
yang dilayani bukan optimum, dan itu perlu diukur, bukan diperdebatkan.

alpha = 1,0 berarti murni ALS. alpha = 0,0 berarti murni CBF. Campuran di
antaranya memakai min-max per akun persis seperti evaluator.

Luaran: docs/evidence/phase2/alpha_sweep_full.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.phase2 import config
from src.phase2.evaluate import (als_ranker, build_tfidf, cbf_ranker,
                                 evaluate_ranking, minmax, rank_topk)
from src.phase2.generator import generate_interactions
from src.phase2.run_eval import (BASE_SHAPE, EFFECTIVE_SINCE, SEEDS, S_GRID,
                                 effective_catalog)
from src.phase2.split import draft_q80, split_catalog, split_interactions
from src.phase2.train_als import build_csr
from src.phase2.sweep_factors import fit_with_factors

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs/evidence/phase2/alpha_sweep_full.json"
K = 10


def ndcg(rankings, relevant, accounts):
    return float(np.mean([evaluate_ranking(rankings[a], relevant.get(a, set()),
                                            K)["ndcg@10"] for a in accounts]))


def run_point(gen_seed: int, s: float, factors: list[int],
              alphas: list[float]) -> dict:
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
    train_c, _ = split_catalog(catalog, cutoff)
    mat, uidx, iidx = build_csr(train_i)

    relevant = dev_i.groupby("dummy_user_id")["nid"].apply(set).to_dict()
    items = sorted(catalog["nid"].unique())
    accounts = sorted(set(dev_i["dummy_user_id"]))

    _, tfidf = build_tfidf(train_c, catalog)
    row_of = {n: i for i, n in enumerate(catalog["nid"])}
    cbf_fn = cbf_ranker(tfidf, row_of, train_i, items)
    cbf_m = {a: minmax(cbf_fn(a)) for a in accounts}

    out = {"seed": gen_seed, "s": s, "n_accounts": len(accounts),
           "curves": {}}
    for f in factors:
        model = fit_with_factors(mat, f)
        als_fn = als_ranker(model, uidx, iidx, items)
        als_m = {a: minmax(als_fn(a)) for a in accounts}
        curve = {}
        for alpha in alphas:
            def hyb(a, alpha=alpha):
                return alpha * als_m[a] + (1 - alpha) * cbf_m[a]
            curve[f"{alpha:.1f}"] = ndcg(
                rank_topk(hyb, items, accounts, K), relevant, accounts)
        out["curves"][str(f)] = curve
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.phase2.sweep_alpha")
    ap.add_argument("--factors", default="64,128")
    ap.add_argument("--alphas", default="0.4,0.6,0.8,0.9,1.0")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    factors = [int(x) for x in args.factors.split(",")]
    alphas = [float(x) for x in args.alphas.split(",")]

    points = []
    for gen_seed in SEEDS:
        for s in S_GRID:
            pt = run_point(gen_seed, s, factors, alphas)
            points.append(pt)
            cells = []
            for f in factors:
                best_a = max(pt["curves"][str(f)],
                             key=pt["curves"][str(f)].get)
                cells.append(f"f{f}: best alpha {best_a} "
                             f"({pt['curves'][str(f)][best_a]:.6f})")
            print(f"seed={gen_seed} s={s}: " + "  ".join(cells), flush=True)

    means = {str(f): {f"{a:.1f}": float(np.mean(
        [p["curves"][str(f)][f"{a:.1f}"] for p in points])) for a in alphas}
        for f in factors}
    out = {
        "protocol": {
            "point": "9 titik sensitivitas (seed 1-3 x s 0.9/1.1/1.3)",
            "metric": f"NDCG@{K}, peringkat penuh katalog per akun",
            "alphas": alphas, "factors": factors,
            "note": "alpha 1.0 = ALS murni; 0.0 = CBF murni",
            "effective_catalog_since": EFFECTIVE_SINCE,
        },
        "means": means,
        "points": points,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print()
    for f in factors:
        print(f"faktor {f}: " + "  ".join(
            f"a{a}={means[str(f)][f'{a:.1f}']:.6f}" for a in alphas))
    print("->", args.out)


if __name__ == "__main__":
    main()
