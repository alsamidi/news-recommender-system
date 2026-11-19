"""CLI: summarize the sensitivity matrix into models/indo_eval.json (Task 12).

  python -m src.phase2.write_eval

Reads docs/evidence/phase2/sensitivity_matrix.json, computes the winner
hybrid alpha (mean NDCG@10 across points), and writes models/indo_eval.json
(pattern of metrics_source_of_truth: every number traceable to a JSON in
docs/evidence/). Also prints the agreed caveats (Table-D-style n column;
popularity-first property of simulated view data).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.phase2.evaluate import ALPHA_GRID

REPO = Path(__file__).resolve().parents[2]
MATRIX = REPO / "docs/evidence/phase2/sensitivity_matrix.json"
OUT = REPO / "models/indo_eval.json"


def main():
    matrix = json.loads(MATRIX.read_text())
    points = matrix["points"]

    summary = {
        "corpus": "indo",
        "protocol": matrix["protocol"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_points": len(points),
        "winner_alpha_by_mean_ndcg": None,
        "alpha_grid_mean_ndcg": {
            str(a): float(np.mean([p["systems"][f"hybrid_a{a}"]["ndcg@10_mean"]
                                   for p in points]))
            for a in ALPHA_GRID},
        "per_point": [
            {"seed": p["seed"], "s": p["s"],
             "cutoff_draft": p["cutoff_draft"],
             "train_events": p["train_events"],
             "dev_events": p["dev_events"],
             "n_accounts": p["systems"]["popularity"]["n_accounts"],
             "winner_alpha": p["winner_alpha_by_ndcg"],
             "ndcg@10": {name: sys_["ndcg@10_mean"]
                         for name, sys_ in p["systems"].items()},
             "ap@10": {name: sys_["ap@10_mean"]
                       for name, sys_ in p["systems"].items()},
             "recall@10": {name: sys_["recall@10_mean"]
                           for name, sys_ in p["systems"].items()},
             # metrics the locked summary used to omit (map = AP alias)
             "precision@10": {name: sys_["precision@10_mean"]
                               for name, sys_ in p["systems"].items()},
             "f1@10": {name: sys_["f1@10_mean"]
                        for name, sys_ in p["systems"].items()},
             "map@10": {name: sys_["map@10_mean"]
                          for name, sys_ in p["systems"].items()},
             } for p in points],
        "caveats": [
            "Every number is the mean over accounts of one seed/s cell; the "
            "account count n is per-point in per_point.n_accounts — do not "
            "compare cells with different n without naming n (Table-D rule).",
            "Interactions are SIMULATED (view-only, Gate B model): the "
            "popularity baseline an upper-bound-flavored reference because "
            "the generator's own popularity process defines the signal; "
            "absolute NDCG scale is a property of the task, not a bug.",
            "ALS scores only items with factors (78.9% of the effective "
            "catalog, Gate C); factorless dev items get a floor score (-1.0) "
            "and only surface when nothing better exists.",
            "Full dev-catalog ranking (no sampled negatives); relevant = "
            "account's own dev views; k=10.",
        ],
    }
    winner = max(summary["alpha_grid_mean_ndcg"],
                 key=summary["alpha_grid_mean_ndcg"].get)
    summary["winner_alpha_by_mean_ndcg"] = float(winner)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"wrote {OUT} (winner alpha = {winner})")


if __name__ == "__main__":
    main()
