"""CLI: evaluate 4 systems over the sensitivity matrix (Task 11).

  python -m src.phase2.run_eval [--quick]

For each point (seed in {1,2,3} x powerlaw_s in {0.9,1.1,1.3}):
regenerate interactions (frozen Gate B shape: n=600, reads 60-180,
recency 180, drift 0.2), re-draft the q80 cutoff, re-fit ALS (v1 defaults,
per-point seed), and evaluate popularity/CBF/ALS/hybrid(alpha grid) on the
full dev catalog. All 12 points land in
docs/evidence/phase2/sensitivity_matrix.json — a matrix, not one number.

`--quick` runs the base point only (seed=42, s=1.1) as a smoke build.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.phase2 import config
from src.phase2.evaluate import ALPHA_GRID, evaluate_point
from src.phase2.generator import generate_interactions
from src.phase2.split import draft_q80, split_catalog, split_interactions
from src.phase2.train_als import ALS_PARAMS, build_csr, fit_als

REPO = Path(__file__).resolve().parents[2]
MATRIX_OUT = REPO / "docs/evidence/phase2/sensitivity_matrix.json"

# Locked Gate B shape (Task 8); sensitivity varies ONLY seed and powerlaw_s.
BASE_SHAPE = {"n_accounts": 600, "reads_per_account": (60, 180),
              "recency_days": 180, "category_drift": 0.2}
SEEDS = (1, 2, 3)
S_GRID = (0.9, 1.1, 1.3)
EFFECTIVE_SINCE = "2025-09-01"


def effective_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    ts = pd.Timestamp(EFFECTIVE_SINCE, tz="UTC")
    return catalog[catalog["published_at"] >= ts].reset_index(drop=True)


def run_point(gen_seed: int, s: float) -> dict:
    catalog = pd.read_parquet(REPO / config.CATALOG_OUT)
    eff = effective_catalog(catalog)
    cfg = config.GeneratorConfig(
        n_accounts=BASE_SHAPE["n_accounts"],
        reads_per_account=BASE_SHAPE["reads_per_account"],
        powerlaw_s=s, recency_days=BASE_SHAPE["recency_days"],
        category_drift=BASE_SHAPE["category_drift"], seed=gen_seed)
    inter = generate_interactions(eff[["nid", "category", "source",
                                       "published_at"]], cfg)
    cutoff = draft_q80(inter)
    train_i, dev_i = split_interactions(inter, cutoff)
    train_c, dev_c = split_catalog(catalog, cutoff)

    mat, uidx, iidx = build_csr(train_i)
    model = fit_als(mat)

    report = evaluate_point(
        catalog, train_c, train_i, dev_i,
        als_model=model, uidx=uidx, iidx=iidx, alphas=ALPHA_GRID)
    # winner alpha by mean NDCG@10 over the hybrid grid
    hyb = {a: report[f"hybrid_a{a}"]["ndcg@10_mean"] for a in ALPHA_GRID}
    return {
        "seed": gen_seed, "s": s,
        "cutoff_draft": str(cutoff),
        "train_events": int(len(train_i)), "dev_events": int(len(dev_i)),
        "als_train_items": int(mat.shape[1]),
        "systems": report,
        "winner_alpha_by_ndcg": max(hyb, key=hyb.get),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.phase2.run_eval")
    ap.add_argument("--quick", action="store_true",
                    help="base point only (seed=42, s=1.1), not persisted "
                         "into the matrix count")
    args = ap.parse_args(argv)

    if args.quick:
        print(json.dumps(run_point(42, 1.1), indent=2)[:2000])
        return

    points = []
    for gen_seed in SEEDS:
        for s in S_GRID:
            print(f"=== seed={gen_seed} s={s}", flush=True)
            points.append(run_point(gen_seed, s))
    matrix = {
        "protocol": {
            "metrics": "NDCG@10, AP@10, Recall@10; full dev-catalog ranking",
            "frozen_shape": {**BASE_SHAPE,
                             "reads_per_account": list(BASE_SHAPE["reads_per_account"])},
            "seeds": list(SEEDS), "s_grid": list(S_GRID),
            "alpha_grid": list(ALPHA_GRID),
            "als_params": ALS_PARAMS,
            "effective_catalog_since": EFFECTIVE_SINCE,
        },
        "points": points,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    MATRIX_OUT.write_text(json.dumps(matrix, indent=2))
    print(f"sensitivity matrix ({len(points)} points) -> {MATRIX_OUT}")


if __name__ == "__main__":
    main()
