"""Metrics module for the comparison notebook (goal: metric comparison).

Every metric is imported from the locked evaluator (`src/phase2/evaluate.py`)
so the notebook and `models/indo_eval.json` share one implementation; this
module only adds the @K-suffixed wrappers the notebook and the comparison
JSON use.

The functions are pure and cheap to hand-verify: see
`tests/phase2/test_metrics_ext.py` for the hand-computed cases.
"""
from __future__ import annotations

from src.phase2.evaluate import (f1_at_k, map_at_k, ndcg_at_k,
                                 precision_at_k, recall_at_k)


# precision_at_k, f1_at_k and map_at_k come from the locked evaluator:
# one implementation only, so the notebook numbers and the numbers in
# models/indo_eval.json cannot drift apart.


def ndcg(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    return ndcg_at_k(ranked_ids, relevant, k)


def recall(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    return recall_at_k(ranked_ids, relevant, k)


METRICS = {
    "precision": precision_at_k,
    "recall": recall,
    "f1": f1_at_k,
    "map": map_at_k,
    "ndcg": ndcg,
}
