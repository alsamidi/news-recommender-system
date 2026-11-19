"""Measure the ranking path the web app actually serves, over 9 points.

  python -m src.phase2.eval_session [--out PATH] [--window 50]

Why this exists: `models/indo_eval.json` scores `recommend_user` — a WARM
account, scored with the ALS user vector trained for it. The web layer never
calls that path. `src/web/services/feed.py` sends the account's last 50 nids
as `history` to POST /recommend, which lands in
`IndoHybridRecommender.recommend_session`: a COLD session profile (mean of
the ALS item factors of the history items) blended with the TF-IDF profile
at alpha = cf_weight (0.8). Same catalog, same metric, different profile —
so the served number is not the evaluated number, and the size of the gap
has to be measured rather than argued.

Four rankings per point, all on the same dev split, full dev-catalog
candidates, NDCG@10 over accounts:
  warm_user        : als_ranker(model, uidx, iidx, dev_items) — the official
                     path; asserted equal to models/indo_eval.json
                     ndcg@10.als at 1e-9 (hard fail otherwise).
  session_hybrid   : the served path — session ALS profile from the last
                     `window` TRAIN nids, 0.8*minmax(als) + 0.2*minmax(cbf),
                     session items masked, exactly `recommend_session`.
  session_als_only : the same session profile at alpha = 1.0, so the CBF
                     contribution to the drop is visible on its own.
  popularity       : TRAIN view counts desc, nid asc (feed fallback).

Output: docs/evidence/phase2/session_path_eval.json
"""
from __future__ import annotations

import argparse
import gc
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.phase2 import config
from src.phase2.evaluate import (als_ranker, build_tfidf, cbf_ranker,
                                 evaluate_ranking, minmax, popularity_ranker,
                                 rank_topk)
from src.phase2.generator import generate_interactions
from src.phase2.run_eval import (BASE_SHAPE, EFFECTIVE_SINCE, SEEDS, S_GRID,
                                 effective_catalog)
from src.phase2.split import draft_q80, split_catalog, split_interactions
from src.phase2.train_als import ALS_PARAMS, build_csr, fit_als

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs/evidence/phase2/session_path_eval.json"
OFFICIAL = REPO / "models/indo_eval.json"
SERVING_CFG = REPO / "configs/indo_serving.yaml"
K = 10
WINDOW = 50  # src/web/config.py WEB_HISTORY_LIMIT default
TOL = 1e-9


def served_alpha() -> float:
    """alpha as served: configs/indo_serving.yaml model.cf_weight."""
    cfg = yaml.safe_load(SERVING_CFG.read_text())
    return float(cfg["model"]["cf_weight"])


def mean_ndcg(rankings, relevant, accounts, k=K) -> float:
    return float(np.mean([evaluate_ranking(rankings[a],
                                            relevant.get(a, set()),
                                            k)["ndcg@10"]
                          for a in accounts]))


def train_windows(train_events: pd.DataFrame, catalog_nids: set[str],
                  window: int) -> dict[str, list[str]]:
    """Last `window` unique TRAIN nids per account, newest first.

    Mirrors the web store (`history_nids`: newest first, unique nid, LIMIT
    window) and the `history` list POST /recommend receives. Nids outside
    the catalog are skipped (serving drops them in `recommend_session`).
    """
    t = pd.to_datetime(train_events["occurred_at"], utc=True)
    ordered = (train_events.assign(_t=t)
               .sort_values("_t", ascending=False, kind="mergesort"))
    out: dict[str, list[str]] = {}
    for account, g in ordered.groupby("dummy_user_id", sort=False):
        seen: set[str] = set()
        keep: list[str] = []
        for nid in g["nid"]:
            if nid in seen or nid not in catalog_nids:
                continue
            seen.add(nid)
            keep.append(nid)
            if len(keep) == window:
                break
        out[account] = keep
    return out


def session_als_ranker(model, iidx: dict, windows: dict[str, list[str]],
                       dev_items: list[str]):
    """ALS scores from a COLD session profile — `_als_scores(None, ...)`.

    Profile = mean of the item factors of the session nids that have factors
    (serving's `_item_row` path); items without factors keep the -1.0 floor.
    """
    i_f = model.item_factors
    dev_rows = np.array([iidx.get(n, -1) for n in dev_items])
    known = np.flatnonzero(dev_rows >= 0)

    def score(account):
        rows = [iidx[n] for n in windows.get(account, ()) if n in iidx]
        if not rows:
            return np.full(len(dev_items), -1.0)
        profile = i_f[rows].mean(axis=0)
        out = np.full(len(dev_items), -1.0)
        if len(known):
            out[known] = i_f[dev_rows[known]] @ profile
        return out

    return score


def session_blend(als_m, cbf_m, masks, row_of, alpha):
    """a*minmax(als) + (1-a)*minmax(cbf), then mask the session items.

    Same order as `IndoHybridRecommender.recommend_session` (blend, then
    `_mask`), and the same minmax (imported from evaluate.py).
    """
    def score(account):
        s = alpha * als_m[account] + (1.0 - alpha) * cbf_m[account]
        for nid in masks.get(account, ()):
            pos = row_of.get(nid)
            if pos is not None:
                s[pos] = -np.inf
        return s

    return score


def run_point(gen_seed: int, s: float, window: int = WINDOW,
              alpha: float | None = None) -> dict:
    alpha = served_alpha() if alpha is None else alpha
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
    model = fit_als(mat)

    _, tfidf = build_tfidf(train_c, catalog)
    row_of = {n: i for i, n in enumerate(catalog["nid"])}
    dev_items = sorted(catalog["nid"].unique())
    # the catalog frame is only needed for nids from here on; drop the text
    # columns so nine points fit in memory one after another
    catalog_nids = set(dev_items)
    del train_c, catalog
    gc.collect()

    accounts = sorted(set(dev_i["dummy_user_id"]))
    relevant = dev_i.groupby("dummy_user_id")["nid"].apply(set).to_dict()

    # (a) official warm path
    warm = mean_ndcg(rank_topk(als_ranker(model, uidx, iidx, dev_items),
                               dev_items, accounts, K), relevant, accounts)

    # (b)/(c) served cold-session path
    windows = train_windows(train_i, catalog_nids, window)
    session_events = pd.DataFrame(
        [(a, n) for a, nids in windows.items() for n in nids],
        columns=["dummy_user_id", "nid"])
    cbf_fn = cbf_ranker(tfidf, row_of, session_events, dev_items)
    als_s_fn = session_als_ranker(model, iidx, windows, dev_items)
    cbf_m = {a: minmax(cbf_fn(a)) for a in accounts}
    als_m = {a: minmax(als_s_fn(a)) for a in accounts}

    hybrid = mean_ndcg(rank_topk(
        session_blend(als_m, cbf_m, windows, row_of, alpha),
        dev_items, accounts, K), relevant, accounts)
    als_only = mean_ndcg(rank_topk(
        session_blend(als_m, cbf_m, windows, row_of, 1.0),
        dev_items, accounts, K), relevant, accounts)

    # reference: the feed's popularity fallback
    pop = mean_ndcg(rank_topk(popularity_ranker(train_i, dev_items),
                              dev_items, accounts, K), relevant, accounts)

    return {
        "seed": gen_seed, "s": s,
        "cutoff_draft": str(cutoff),
        "train_events": int(len(train_i)), "dev_events": int(len(dev_i)),
        "n_accounts": len(accounts),
        "n_als_items": int(mat.shape[1]),
        "warm_user": warm,
        "session_hybrid": hybrid,
        "session_als_only": als_only,
        "popularity": pop,
        "ratio_session_hybrid_over_warm_user": hybrid / warm if warm else None,
    }


def official_als() -> dict[tuple[int, float], float]:
    """models/indo_eval.json ndcg@10.als keyed by (seed, s)."""
    doc = json.loads(OFFICIAL.read_text())
    return {(int(p["seed"]), round(float(p["s"]), 6)): float(p["ndcg@10"]["als"])
            for p in doc["per_point"]}


def assert_official(points: list[dict], tol: float = TOL) -> None:
    """Hard fail if the warm path stops reproducing the locked evaluation."""
    ref = official_als()
    assert len(ref) == 9, f"expected 9 official points, got {len(ref)}"
    for p in points:
        key = (p["seed"], round(p["s"], 6))
        assert key in ref, f"point {key} missing from {OFFICIAL.name}"
        got, want = p["warm_user"], ref[key]
        if abs(got - want) > tol:
            raise AssertionError(
                f"warm_user mismatch at seed={key[0]} s={key[1]}: "
                f"got {got!r}, indo_eval.json has {want!r}, "
                f"diff {got - want:.3e} > tol {tol:.0e}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.phase2.eval_session")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--window", type=int, default=WINDOW,
                    help="history window sent to POST /recommend (default 50)")
    args = ap.parse_args(argv)
    alpha = served_alpha()

    points = []
    for gen_seed in SEEDS:
        for s in S_GRID:
            pt = run_point(gen_seed, s, window=args.window, alpha=alpha)
            points.append(pt)
            print(f"seed={gen_seed} s={s}: warm={pt['warm_user']:.6f} "
                  f"session={pt['session_hybrid']:.6f} "
                  f"als_only={pt['session_als_only']:.6f} "
                  f"pop={pt['popularity']:.6f} "
                  f"ratio={pt['ratio_session_hybrid_over_warm_user']:.3f}",
                  flush=True)

    assert_official(points)

    names = ("warm_user", "session_hybrid", "session_als_only", "popularity")
    means = {n: float(np.mean([p[n] for p in points])) for n in names}
    out = {
        "protocol": {
            "points": len(points),
            "seeds": list(SEEDS), "s_grid": list(S_GRID),
            "metric": f"NDCG@{K}",
            "ranking": "full dev-catalog per account, no sampled negatives, "
                       "k=10; relevant = account's dev views",
            "n_accounts": sorted({p["n_accounts"] for p in points}),
            "alpha": alpha,
            "alpha_source": "configs/indo_serving.yaml model.cf_weight",
            "window": args.window,
            "window_source": "src/web/config.py WEB_HISTORY_LIMIT default",
            "frozen_shape": {**BASE_SHAPE,
                             "reads_per_account":
                                 list(BASE_SHAPE["reads_per_account"])},
            "als_params": ALS_PARAMS,
            "effective_catalog_since": EFFECTIVE_SINCE,
            "warm_reference": "models/indo_eval.json per_point ndcg@10.als "
                              f"(asserted at {TOL:.0e})",
            "note": "warm_user is recommend_user (ALS user vector); "
                    "session_hybrid is the served recommend_session path "
                    "(cold profile from the last window nids); "
                    "session_als_only is the same profile at alpha=1.0",
        },
        "means": means,
        "mean_ratio_session_hybrid_over_warm_user": (
            means["session_hybrid"] / means["warm_user"]),
        "per_point": points,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print()
    print("  ".join(f"{n}={means[n]:.6f}" for n in names))
    print(f"session_hybrid/warm_user = "
          f"{out['mean_ratio_session_hybrid_over_warm_user']:.3f}")
    print("->", args.out)


if __name__ == "__main__":
    main()
